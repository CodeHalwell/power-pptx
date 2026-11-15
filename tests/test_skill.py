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

    def it_accepts_a_str_target(self, tmp_path):
        from power_pptx.skill import install_skill

        dest = install_skill(target=str(tmp_path / "power-pptx"))

        assert (dest / "SKILL.md").is_file()

    def it_installs_into_an_existing_empty_directory(self, tmp_path):
        from power_pptx.skill import install_skill

        target = tmp_path / "power-pptx"
        target.mkdir()

        install_skill(target=target)

        assert (target / "SKILL.md").is_file()
        assert (target / "references").is_dir()

    def but_it_refuses_to_replace_a_directory_that_is_not_this_skill(self, tmp_path):
        """`install ~/.claude/skills` must not wipe the user's other skills."""
        from power_pptx.skill import install_skill

        skills_dir = tmp_path / "skills"
        other = skills_dir / "another-skill"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("---\nname: another-skill\n---\n")
        (skills_dir / "notes.txt").write_text("keep me")

        with pytest.raises(FileExistsError, match="not a power-pptx skill install"):
            install_skill(target=skills_dir)

        assert (other / "SKILL.md").read_text() == "---\nname: another-skill\n---\n"
        assert (skills_dir / "notes.txt").read_text() == "keep me"
        assert sorted(p.name for p in skills_dir.iterdir()) == ["another-skill", "notes.txt"]

    def and_it_refuses_to_replace_a_different_skill(self, tmp_path):
        from power_pptx.skill import install_skill

        target = tmp_path / "some-skill"
        target.mkdir()
        (target / "SKILL.md").write_text("---\nname: some-skill\ndescription: x\n---\n# body\n")

        with pytest.raises(FileExistsError):
            install_skill(target=target)

        assert (target / "SKILL.md").read_text().startswith("---\nname: some-skill\n")

    def and_it_reports_a_file_target_as_not_a_directory(self, tmp_path):
        from power_pptx.skill import install_skill

        target = tmp_path / "power-pptx"
        target.write_text("I am a file")

        with pytest.raises(NotADirectoryError, match="is a file, not a directory"):
            install_skill(target=target)

        assert target.read_text() == "I am a file"

    def and_it_refuses_to_replace_a_symlink(self, tmp_path):
        from power_pptx.skill import install_skill

        real = tmp_path / "real"
        install_skill(target=real)
        link = tmp_path / "link"
        try:
            link.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):  # pragma: no cover - no symlink privilege
            pytest.skip("symbolic links are not available here")

        with pytest.raises(FileExistsError, match="symbolic link"):
            install_skill(target=link)

        assert link.is_symlink()
        assert (real / "SKILL.md").is_file()

    def it_keeps_the_previous_install_when_the_copy_fails(self, tmp_path, monkeypatch):
        import shutil

        from power_pptx.skill import install_skill

        target = tmp_path / "power-pptx"
        install_skill(target=target)
        (target / "SKILL.md").write_text("---\nname: power-pptx\n---\nprevious version\n")

        def failing_copytree(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(shutil, "copytree", failing_copytree)

        with pytest.raises(OSError, match="disk full"):
            install_skill(target=target)

        assert "previous version" in (target / "SKILL.md").read_text()
        assert [p.name for p in tmp_path.iterdir()] == ["power-pptx"]


class DescribeSkillCli:
    def it_installs_into_a_positional_target(self, tmp_path, capsys):
        from power_pptx.skill.__main__ import main

        target = tmp_path / "power-pptx"

        assert main(["install", str(target)]) == 0
        assert (target / "SKILL.md").is_file()
        assert str(target) in capsys.readouterr().out

    def it_installs_into_a_target_given_as_an_option(self, tmp_path):
        """README documents `install --target PATH`."""
        from power_pptx.skill.__main__ import main

        target = tmp_path / "skills" / "power-pptx"

        assert main(["install", "--target", str(target)]) == 0
        assert (target / "SKILL.md").is_file()

    def but_it_rejects_a_target_given_both_ways(self, tmp_path, capsys):
        from power_pptx.skill.__main__ import main

        with pytest.raises(SystemExit) as excinfo:
            main(["install", str(tmp_path / "a"), "--target", str(tmp_path / "b")])

        assert excinfo.value.code == 2
        assert not (tmp_path / "a").exists()
        assert not (tmp_path / "b").exists()

    def it_exits_non_zero_without_deleting_an_unrelated_directory(self, tmp_path, capsys):
        from power_pptx.skill.__main__ import main

        skills_dir = tmp_path / "skills"
        (skills_dir / "another-skill").mkdir(parents=True)
        (skills_dir / "another-skill" / "SKILL.md").write_text("---\nname: another-skill\n---\n")

        assert main(["install", str(skills_dir)]) == 1

        assert (skills_dir / "another-skill" / "SKILL.md").is_file()
        assert not (skills_dir / "SKILL.md").exists()
        err = capsys.readouterr().err
        assert "refusing to replace" in err
        assert str(skills_dir / "power-pptx") in err

    def it_reports_a_file_target_cleanly(self, tmp_path, capsys):
        from power_pptx.skill.__main__ import main

        target = tmp_path / "a-file"
        target.write_text("x")

        assert main(["install", "--target", str(target)]) == 1

        assert target.read_text() == "x"
        assert "is a file, not a directory" in capsys.readouterr().err

    def it_honours_no_overwrite(self, tmp_path, capsys):
        from power_pptx.skill.__main__ import main

        target = tmp_path / "power-pptx"
        assert main(["install", str(target)]) == 0

        assert main(["install", str(target), "--no-overwrite"]) == 1
        assert "refusing to overwrite" in capsys.readouterr().err
