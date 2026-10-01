"""Explicit fixture exercise of session transitions; creates no footage."""

from uuid import UUID, uuid5

from .contracts import Beat, Command, Evidence, Mode, ProductionBrief, Session, ShotReference
from .service import fingerprint


def run_demonstration(service, operation_id, epoch, expiry):
    brief = ProductionBrief(
        "Offline session example",
        "Exercise planning and take acknowledgements with labeled fixtures. No AI, camera or motors.",
        12000,
        "9:16",
    )
    created = service.create(operation_id, epoch, expiry, brief, Mode.DEMONSTRATION)
    if not created["ok"]:
        return created
    if created["replayed"]:
        return {**created, **service.repository.inspect(created["session"]["session_id"])}
    session = Session.parse(created["session"])
    namespace = UUID(operation_id)
    shot = ShotReference(
        str(uuid5(namespace, "scene")),
        str(uuid5(namespace, "shot")),
        1,
        fingerprint({"example": "offline session", "version": 1}),
        12000,
        "fixture",
        (
            Beat(str(uuid5(namespace, "beat-1")), 0, 4000, "Introduce the product — example only."),
            Beat(str(uuid5(namespace, "beat-2")), 4000, 12000, "Show and hold — example only."),
        ),
    )
    actions = (
        "request_plan",
        "request_rehearsal",
        "mark_ready",
        "request_record",
        "request_cut",
        "request_review",
        "accept_take",
        "prepare_edit",
    )
    for index, action in enumerate(actions):
        outcome = service.submit(
            Command(str(uuid5(namespace, action)), epoch, expiry, session.scope(), action)
        )
        if not outcome["ok"]:
            return outcome
        session = Session.parse(outcome["session"])
        if outcome["job_id"]:
            outcome = service.complete(
                str(uuid5(namespace, action + "-complete")),
                outcome["job_id"],
                session.scope(),
                epoch,
                expiry,
                Evidence("fixture", "offline-session-example", index, service.clock(), epoch, "session"),
                shot if action == "request_plan" else None,
            )
            if not outcome["ok"]:
                return outcome
            session = Session.parse(outcome["session"])
    return {
        "ok": True,
        "code": "demonstration_complete",
        "session": session.wire(),
        "message": "Session transitions exercised with fixtures. No real recording or movement occurred.",
        "real_media_verified": False,
        "replayed": False,
    }
