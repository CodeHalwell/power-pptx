"""Bundled Claude skill ships with the package and installs cleanly."""

from __future__ import annotations

import pytest


class DescribeSkillRoot:
    def it_returns_a_directory_containing_skill_md(self):
        from power_pptx.skill import skill_root

        root = skill_root()
        assert root.is_dir()
        assert (root / "SKILL.md").is_file()
        assert (root / "references").is_dir()


class DescribeInstallSkill:
    def it_copies_skill_md_and_references_into_target(self, tmp_path):
        from power_pptx.skill import install_skill

        target = tmp_path / "skills" / "power-pptx"
        dest = install_skill(target=target)

        assert dest == target
        assert (dest / "SKILL.md").is_file()
        assert (dest / "references").is_dir()
        # At least one reference doc shipped
        refs = list((dest / "references").glob("*.md"))
        assert refs, "expected at least one reference markdown file"

    def it_overwrites_an_existing_install_by_default(self, tmp_path):
        from power_pptx.skill import install_skill

        target = tmp_path / "skill"
        install_skill(target=target)
        # Add a stray file we expect to be wiped.
        stray = target / "stray.md"
        stray.write_text("from a previous version")
        install_skill(target=target)
        assert not stray.exists()

    def it_refuses_to_overwrite_when_no_overwrite(self, tmp_path):
        from power_pptx.skill import install_skill

        target = tmp_path / "skill"
        install_skill(target=target)
        with pytest.raises(FileExistsError):
            install_skill(target=target, overwrite=False)
