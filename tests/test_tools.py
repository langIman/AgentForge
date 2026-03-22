"""测试工具模块：bash、file_ops、skill"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.config import WORKSPACE_ROOT
from src.tools.bash import _is_dangerous, bash
from src.tools.file_ops import _safe_path, edit_file, read_file, write_file
from src.tools.skill import SkillLoader


# ─── Bash工具 ───


class TestBash:
    @pytest.fixture(autouse=True)
    def setup_cwd(self, tmp_path):
        self._patcher = patch("src.tools.bash.WORKSPACE_ROOT", tmp_path)
        self._patcher.start()
        yield
        self._patcher.stop()

    def test_echo(self):
        result = bash.invoke({"command": "echo hello"})
        assert "hello" in result

    def test_dangerous_command_blocked(self):
        result = bash.invoke({"command": "rm -rf /"})
        assert "[BLOCKED]" in result

    def test_dangerous_detection(self):
        assert _is_dangerous("rm -rf /") is True
        assert _is_dangerous("RM -RF /") is True
        assert _is_dangerous("echo hello") is False
        assert _is_dangerous("mkfs.ext4 /dev/sda") is True

    def test_timeout(self):
        with patch("src.tools.bash.BASH_TIMEOUT", 1):
            result = bash.invoke({"command": "sleep 10"})
            assert "[TIMEOUT]" in result

    def test_exit_code_shown(self):
        result = bash.invoke({"command": "true"})
        assert "exit code: 0" in result or result.strip() == ""


# ─── 文件操作工具 ───


class TestFileOps:
    @pytest.fixture(autouse=True)
    def setup_workspace(self, tmp_path):
        """使用临时目录作为workspace"""
        self._orig = os.environ.get("WORKSPACE_ROOT")
        os.environ["WORKSPACE_ROOT"] = str(tmp_path)
        # Patch WORKSPACE_ROOT
        self._patcher = patch("src.tools.file_ops.WORKSPACE_ROOT", tmp_path)
        self._patcher.start()
        self.workspace = tmp_path
        yield
        self._patcher.stop()
        if self._orig:
            os.environ["WORKSPACE_ROOT"] = self._orig

    def test_write_and_read(self):
        result = write_file.invoke({"file_path": str(self.workspace / "test.txt"), "content": "hello world"})
        assert "已写入" in result

        result = read_file.invoke({"file_path": str(self.workspace / "test.txt")})
        assert "hello world" in result

    def test_read_nonexistent(self):
        result = read_file.invoke({"file_path": str(self.workspace / "nope.txt")})
        assert "[ERROR]" in result

    def test_edit_file(self):
        path = str(self.workspace / "edit_test.txt")
        write_file.invoke({"file_path": path, "content": "foo bar baz"})
        result = edit_file.invoke({"file_path": path, "old_string": "bar", "new_string": "qux"})
        assert "已替换" in result

        content = read_file.invoke({"file_path": path})
        assert "qux" in content
        assert "bar" not in content

    def test_edit_not_found(self):
        path = str(self.workspace / "edit2.txt")
        write_file.invoke({"file_path": path, "content": "abc"})
        result = edit_file.invoke({"file_path": path, "old_string": "xyz", "new_string": "123"})
        assert "[ERROR]" in result

    def test_sandbox_violation(self):
        with patch("src.tools.file_ops.WORKSPACE_ROOT", Path("/tmp/sandbox_test_dir")):
            result = read_file.invoke({"file_path": "/etc/passwd"})
            assert "[SANDBOX ERROR]" in result

    def test_write_creates_subdirectory(self):
        path = str(self.workspace / "sub" / "dir" / "file.txt")
        result = write_file.invoke({"file_path": path, "content": "nested"})
        assert "已写入" in result

    def test_read_with_offset_limit(self):
        path = str(self.workspace / "lines.txt")
        content = "\n".join(f"line {i}" for i in range(100))
        write_file.invoke({"file_path": path, "content": content})

        result = read_file.invoke({"file_path": path, "offset": 10, "limit": 5})
        assert "line 10" in result
        assert "line 14" in result


# ─── 技能系统 ───


class TestSkillLoader:
    @pytest.fixture
    def loader(self, tmp_path):
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        # 创建测试技能
        test_skill = skill_dir / "test-skill"
        test_skill.mkdir()
        (test_skill / "SKILL.md").write_text("# Test Skill\n\nThis is a test skill.\n\n## Usage\nDo things.")
        return SkillLoader(skill_dir)

    def test_discover(self, loader):
        skills = loader._discover()
        assert "test-skill" in skills

    def test_get_descriptions(self, loader):
        desc = loader.get_descriptions()
        assert "test-skill" in desc
        assert "Test Skill" in desc

    def test_get_content(self, loader):
        content = loader.get_content("test-skill")
        assert "This is a test skill" in content

    def test_get_content_not_found(self, loader):
        content = loader.get_content("nonexistent")
        assert "[ERROR]" in content

    def test_cache(self, loader):
        loader.get_content("test-skill")
        assert "test-skill" in loader._cache
        # 第二次从缓存读取
        content = loader.get_content("test-skill")
        assert "This is a test skill" in content
