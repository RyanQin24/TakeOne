"""Offline fixtures only. These tests do not download or claim third-party models."""
from pathlib import Path
import copy
import importlib.util
import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "payload/packages"))  # Isolated test harness, not an app path shim.
from takeone.asset_library.catalog import AssetCatalog
from takeone.asset_library.importer import extract_pack, import_zip
from takeone.asset_library.inspect import gltf_document, inspect_model
from takeone.asset_library.providers import discover_zip, download_pack, validate_url
from takeone.asset_library.storage import library_lock, library_path, safe_relative

spec = importlib.util.spec_from_file_location("kit_installer", KIT / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
PACK = {"id":"fixture-pack", "name":"Authored test fixture", "provider":"kenney",
        "page_url":"https://kenney.nl/assets/furniture-kit", "license":"CC0-1.0",
        "author":"Test fixture", "kind":"prop", "tags":["furniture"]}


def model_document():
    return {"asset":{"version":"2.0"}, "scene":0, "scenes":[{"nodes":[0]}],
            "nodes":[{"mesh":0}], "meshes":[{"primitives":[{"attributes":{"POSITION":0}}]}],
            "buffers":[{"byteLength":36}], "bufferViews":[{"buffer":0,"byteLength":36}],
            "accessors":[{"bufferView":0,"componentType":5126,"count":3,"type":"VEC3",
                          "min":[0,0,0],"max":[1,1,0]}]}


def glb(document=None):
    document = copy.deepcopy(document or model_document())
    meta = json.dumps(document).encode()
    meta += b" " * ((-len(meta)) % 4)
    binary = struct.pack("<9f", 0,0,0, 1,0,0, 0,1,0)
    length = 12 + 8 + len(meta) + 8 + len(binary)
    return struct.pack("<4sII", b"glTF",2,length) + struct.pack("<II",len(meta),0x4E4F534A) + meta + struct.pack("<II",len(binary),0x004E4942) + binary


def write_zip(path, members):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


class AssetLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.work = Path(self.temporary.name)
        self.project = self.work / "TakeOne"
        (self.project / "packages/takeone").mkdir(parents=True)
        (self.project / "apps/rehearsal/dist").mkdir(parents=True)
        self.archive = write_zip(self.work / "fixture.zip", {"Models/chairWood.glb":glb(), "License.txt":"Authored fixture"})

    def tearDown(self):
        self.temporary.cleanup()

    def test_empty_catalog_is_empty_without_writing(self):
        self.assertEqual(len(AssetCatalog.from_project(self.project)), 0)
        self.assertFalse((library_path(self.project) / "catalog.json").exists())

    def test_valid_portable_relative_path(self):
        self.assertEqual(safe_relative("Models/GLB format/Chair.glb"), Path("Models/GLB format/Chair.glb"))

    def test_reject_unsafe_paths_on_all_platforms(self):
        for value in ["../a", "/tmp/a", "C:/evil", "foo\\bar", "a//b", "a/./b", "aux.txt", "a/NUL", "a/../b", "a.", "a:b"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                safe_relative(value)

    def test_library_symlink_cannot_escape_checkout(self):
        external = self.work / "external"; external.mkdir()
        (self.project / "apps/rehearsal/dist/asset-library").symlink_to(external, target_is_directory=True)
        with self.assertRaises(ValueError):
            library_path(self.project)

    def test_zip_copies_models_not_scripts(self):
        archive = write_zip(self.work / "mixed.zip", {"a.glb":glb(), "run.exe":b"x", "auto.py":b"x", "README.txt":b"license"})
        target = self.work / "out"; target.mkdir()
        extract_pack(archive, target)
        self.assertEqual({path.name for path in target.iterdir()}, {"a.glb", "README.txt"})

    def test_zip_path_failure_happens_before_writes(self):
        archive = write_zip(self.work / "bad.zip", {"good.glb":glb(), "../escape.txt":b"x"})
        target = self.work / "out"; target.mkdir()
        with self.assertRaises(ValueError): extract_pack(archive, target)
        self.assertEqual(list(target.iterdir()), [])

    def test_zip_windows_case_collision(self):
        archive = write_zip(self.work / "bad.zip", {"A.glb":glb(), "a.glb":glb()})
        with self.assertRaises(ValueError): extract_pack(archive, self.work / "out")

    def test_zip_symlink_rejected(self):
        archive = self.work / "symlink.zip"
        with zipfile.ZipFile(archive,"w") as bundle:
            info = zipfile.ZipInfo("link.glb"); info.create_system = 3; info.external_attr = 0o120777 << 16
            bundle.writestr(info,"/etc/passwd")
        with self.assertRaises(ValueError): extract_pack(archive, self.work / "out")

    def test_zip_member_count_budget(self):
        with patch("takeone.asset_library.importer.MAX_MEMBERS", 1):
            with self.assertRaises(ValueError): extract_pack(self.archive, self.work / "out")

    def test_glb_metadata_and_length(self):
        path = self.work / "triangle.glb"; path.write_bytes(glb())
        self.assertEqual(gltf_document(path)["asset"]["version"], "2.0")
        metadata = inspect_model(path, self.work)
        self.assertEqual(metadata["triangles_nominal"],1)
        self.assertIsNone(metadata["dimensions_m"])
        self.assertEqual(metadata["collision_status"],"not_qualified")

    def test_glb_truncated_header(self):
        path = self.work / "triangle.glb"; path.write_bytes(glb()[:-2])
        with self.assertRaises(ValueError): gltf_document(path)

    def test_external_dependency_rejected(self):
        doc = model_document();doc["buffers"][0]["uri"]="https://example.com/a.bin"
        path=self.work/"a.gltf";path.write_text(json.dumps(doc))
        with self.assertRaises(ValueError): inspect_model(path,self.work)

    def test_sibling_dependency_within_pack(self):
        (self.work/"Models").mkdir();(self.work/"Textures").mkdir()
        doc=model_document();doc["buffers"][0]["uri"]="../Textures/a.bin"
        (self.work/"Textures/a.bin").write_bytes(b"0"*36)
        path=self.work/"Models/a.gltf";path.write_text(json.dumps(doc))
        self.assertEqual(len(inspect_model(path,self.work)["dependencies"]),2)

    def test_missing_dependency_fails(self):
        doc=model_document();doc["buffers"][0]["uri"]="missing.bin"
        path=self.work/"a.gltf";path.write_text(json.dumps(doc))
        with self.assertRaises(ValueError): inspect_model(path,self.work)

    def test_dependency_cannot_escape_pack(self):
        doc=model_document();doc["buffers"][0]["uri"]="../outside.bin"
        path=self.work/"a.gltf";path.write_text(json.dumps(doc))
        with self.assertRaises(ValueError): inspect_model(path,self.work)

    def test_truncated_external_buffer_fails(self):
        doc=model_document();doc["buffers"][0]["uri"]="a.bin"
        path=self.work/"a.gltf";path.write_text(json.dumps(doc));(self.work/"a.bin").write_bytes(b"0")
        with self.assertRaises(ValueError): inspect_model(path,self.work)

    def test_revision_includes_texture_bytes(self):
        doc=model_document();doc["buffers"][0]["uri"]="a.bin";doc["images"]=[{"uri":"texture.png"}]
        path=self.work/"a.gltf";path.write_text(json.dumps(doc));(self.work/"a.bin").write_bytes(b"0"*36)
        texture=self.work/"texture.png";texture.write_bytes(b"original")
        first=inspect_model(path,self.work)
        texture.write_bytes(b"changed")
        second=inspect_model(path,self.work)
        self.assertNotEqual(first["sha256"],second["sha256"])
        self.assertEqual(first["model_sha256"],second["model_sha256"])

    def test_actual_animation_names_and_extensions_retained(self):
        doc=model_document();doc["animations"]=[{"name":"Idle","channels":[],"samplers":[]}]
        doc["extensionsRequired"]=["KHR_draco_mesh_compression"]
        path=self.work/"a.glb";path.write_bytes(glb(doc))
        metadata=inspect_model(path,self.work)
        self.assertEqual(metadata["animations"],[{"index":0,"name":"Idle"}])
        self.assertEqual(metadata["extensions_required"],["KHR_draco_mesh_compression"])

    def test_import_registers_pinned_local_model(self):
        result=import_zip(self.project,self.archive,PACK)
        self.assertEqual(result["imported_renderable_files"],1)
        asset=AssetCatalog.from_project(self.project).search("chair")[0]
        self.assertTrue(asset["asset_id"].startswith("lib:fixture-pack:"))
        self.assertTrue(asset["uri"].startswith("/asset-library/packs/"))
        self.assertEqual(asset["license"],"CC0-1.0")
        self.assertEqual(len(asset["sha256"]),64)

    def test_reimport_is_idempotent(self):
        first=import_zip(self.project,self.archive,PACK)
        second=import_zip(self.project,self.archive,PACK)
        self.assertEqual(first,second)
        self.assertEqual(len(AssetCatalog.from_project(self.project)),1)

    def test_corrupted_snapshot_is_not_silently_accepted(self):
        import_zip(self.project,self.archive,PACK)
        model=next(library_path(self.project).glob("packs/**/*.glb"));model.write_bytes(b"changed")
        with self.assertRaises(ValueError): import_zip(self.project,self.archive,PACK)

    def test_failed_import_preserves_catalog(self):
        import_zip(self.project,self.archive,PACK)
        catalog=library_path(self.project)/"catalog.json";before=catalog.read_bytes()
        bad=write_zip(self.work/"broken.zip",{"b.glb":b"invalid"})
        with self.assertRaises(ValueError): import_zip(self.project,bad,PACK)
        self.assertEqual(catalog.read_bytes(),before)

    def test_new_asset_version_does_not_erase_old(self):
        import_zip(self.project,self.archive,PACK)
        doc=model_document();doc["asset"]["generator"]="changed"
        other=write_zip(self.work/"second.zip",{"Models/chairWood.glb":glb(doc)})
        import_zip(self.project,other,PACK)
        self.assertEqual(len(AssetCatalog.from_project(self.project)),2)

    def test_search_ranking_and_defensive_copy(self):
        document={"schema_version":1,"assets":[
            {"asset_id":"a","name":"chair wood","tags":["furniture"],"pack_id":"demo","kind":"prop","sha256":"1"},
            {"asset_id":"b","name":"table","tags":["chair"],"pack_id":"demo","kind":"prop","sha256":"2"}]}
        catalog=AssetCatalog(document)
        result=catalog.search("chair");self.assertEqual(result[0]["asset_id"],"a")
        result[0]["name"]="changed";self.assertEqual(catalog.get("a")["name"],"chair wood")
        self.assertEqual(catalog.search("chair",kind="character"),[])

    def test_unknown_id_and_wrong_hash_fail(self):
        import_zip(self.project,self.archive,PACK)
        catalog=AssetCatalog.from_project(self.project);asset=catalog.search("chair")[0]
        with self.assertRaises(ValueError): catalog.get("invented")
        with self.assertRaises(ValueError): catalog.get(asset["asset_id"],"wrong")

    def test_import_lock_refuses_concurrent_writer(self):
        path=library_path(self.project)
        with library_lock(path):
            with self.assertRaises(RuntimeError):
                with library_lock(path): pass
        self.assertFalse((path/".import.lock").exists())

    def test_install_preserves_existing_application_files(self):
        original=self.project/"apps/rehearsal/dist/scene-library.js";original.write_bytes(b"CURRENT LOCAL UPGRADE")
        count=installer.install(KIT/"payload",self.project)
        self.assertGreater(count,0)
        self.assertEqual(original.read_bytes(),b"CURRENT LOCAL UPGRADE")
        self.assertEqual(installer.install(KIT/"payload",self.project),0)

    def test_install_conflict_preflight_no_partial_writes(self):
        conflict=self.project/"configs/asset-library/packs.json";conflict.parent.mkdir(parents=True);conflict.write_bytes(b"local")
        with self.assertRaises(FileExistsError): installer.install(KIT/"payload",self.project)
        self.assertFalse((self.project/"packages/takeone/asset_library").exists())
        self.assertEqual(conflict.read_bytes(),b"local")

    def test_installed_cli_search_and_verify(self):
        installer.install(KIT/"payload",self.project)
        import_zip(self.project,self.archive,PACK)
        env={**os.environ,"PYTHONPATH":str(self.project/"packages")}
        command=[sys.executable,"-m","takeone.asset_library","--root",str(self.project)]
        result=subprocess.run(command+["search","chair"],env=env,capture_output=True,text=True,cwd=self.work,check=True)
        self.assertEqual(len(json.loads(result.stdout)),1)
        verified=subprocess.run(command+["verify"],env=env,capture_output=True,text=True,cwd=self.work,check=True)
        self.assertEqual(json.loads(verified.stdout)["assets"],1)

    def test_official_download_link_discovery(self):
        url=discover_zip("https://kenney.nl/assets/furniture-kit",'<a href="/media/free.zip">Continue</a><a href="/media/free.zip">Download</a>')
        self.assertEqual(url,"https://kenney.nl/media/free.zip")
        with self.assertRaises(ValueError): discover_zip("https://kenney.nl/assets/a",'<a href="/a.zip">a</a><a href="/b.zip">b</a>')
        with self.assertRaises(ValueError): discover_zip("https://kenney.nl/assets/a",'<a href="/paid">buy</a>')

    def test_downloader_url_restrictions(self):
        for url in ["http://kenney.nl/a.zip","https://evil.test/a.zip","https://kenney.nl.evil.test/a.zip","https://user:pass@kenney.nl/a.zip","https://127.0.0.1/a.zip"]:
            with self.subTest(url=url),self.assertRaises(ValueError): validate_url(url)

    def test_download_import_pipeline_with_mocked_network(self):
        data=self.archive.read_bytes()
        class FakeOpener:
            def open(self, request, timeout):
                if request.full_url.endswith(".zip"): return io.BytesIO(data)
                return io.BytesIO(b'<a href="https://kenney.nl/media/free.zip">Download</a>')
        result=download_pack(self.project,PACK,FakeOpener())
        self.assertEqual(result["total_catalog_entries"],1)
        evidence=json.loads(next(library_path(self.project).glob("packs/**/TAKEONE-PROVENANCE.json")).read_text())
        self.assertEqual(evidence["origin"]["method"],"official_https")
        # This test mocks HTTPS; it is NOT evidence of a real download.


if __name__ == "__main__": unittest.main()
