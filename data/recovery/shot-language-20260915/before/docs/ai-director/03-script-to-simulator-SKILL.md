# Script-to-simulator skill

The maintained instruction is [robot-film-director/SKILL.md](../../packages/takeone/director/robot-film-director/SKILL.md).
The provider loads that packaged Markdown directly. Editorial profiles live in [filming-skills](../../packages/takeone/director/filming-skills/).

The Python module loads those files and constructs labelled offline examples. The live movement and scene catalogs supply supported IDs and geometry bounds.

See the [scene-aware audit](implementation/05-scene-aware-script-audit.md) for the motivating failures and verification.