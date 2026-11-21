import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from git_env_guard.core import Config, Invalid, classify, disk_files, index_files, scan
from git_env_guard.cli import load_config, main


class GuardTests(unittest.TestCase):
    def test_python_contiguous_not_unrelated(self):
        self.assertEqual((False, False), classify('x.py', 'a="git"\nb="init"', Config()))
        self.assertEqual((True, False), classify('x.py', 'run(["git", "-C", tmp, "init"])', Config()))
        self.assertEqual((True, False), classify('x.py', 'run("git init temp", shell=True)', Config()))
        self.assertEqual((False, False), classify('x.py', '"""git init; --local-env-vars"""\n# git init', Config()))
        self.assertEqual((True, False), classify('x.py', '"""--local-env-vars"""\nrun(["git", "init"])', Config()))

    def test_shell_comments_and_markers(self):
        self.assertEqual((False, False), classify('x.sh', '# git init\necho safe', Config()))
        self.assertEqual((True, False), classify('x.sh', 'git -C "$dir" init\n# git rev-parse --local-env-vars', Config()))
        self.assertEqual((True, True), classify('x.sh', 'unset $(git rev-parse --local-env-vars)\ngit init temp', Config()))

    def test_shell_hashes_inside_words_are_not_comments(self):
        for prefix in ('echo foo#bar;', 'echo ${#values[@]};', 'echo "#quoted";', r'echo \#escaped;'):
            self.assertEqual((True, False), classify('x.sh', prefix + ' git init temp', Config()))
        self.assertEqual((False, False), classify('x.sh', 'echo safe; # git init temp', Config()))
        self.assertEqual((True, False), classify('x.sh', 'echo safe # --local-env-vars\ngit init temp', Config()))

    def test_growing_disk_file_is_read_with_a_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'fixture.py').write_text('x=1')
            stream = io.BytesIO(b'x' * 100)
            original_read = stream.read
            stream.read = unittest.mock.Mock(side_effect=original_read)
            with patch.object(Path, 'open', return_value=stream):
                with self.assertRaises(Invalid):
                    list(disk_files(root, Config(max_bytes=8)))
                stream.read.assert_called_once_with(9)

    def test_no_basename_exemption(self):
        for path in ('git-env-guard.py', 'nested/check-fixture-git-isolation.py', 'git_env_guard/core.py'):
            count, bad = scan([(path, b'run(["git", "init"])')], Config())
            self.assertEqual(1, count)
            self.assertEqual([path], bad)

    def test_fail_closed(self):
        for data in (b'\xff', b'\0', b'def broken(', b'x' * 20):
            with self.assertRaises(Invalid):
                scan([('x.py', data)], Config(max_bytes=10))
        with self.assertRaises(Invalid):
            scan([], Config())

    def test_extensions(self):
        config = Config(extra_globs=['*.fixture'], commands=['init', 'commit'], scrub_markers=['clean_fixture_environment'])
        self.assertEqual((True, True), classify('x.py', 'clean_fixture_environment()\nrun(["git", "commit"])', config))
        self.assertEqual((1, ['case.fixture']), scan([('case.fixture', b'git commit -m example')], config))

    def test_ignore_reason_and_config_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / '.git-env-guard.toml'
            config.write_text('commands=["commit"]\n[ignore]\n"case.py"="detector test"\n')
            parsed = load_config(None, root)
            self.assertIn('init', parsed.commands)
            self.assertIn('commit', parsed.commands)
            self.assertEqual((1, []), scan([('case.py', b'git init'), ('safe.py', b'x=1')], parsed))
            config.unlink()
            (root / 'pyproject.toml').write_text('[tool.git-env-guard]\ncommands=["worktree"]\n')
            self.assertIn('worktree', load_config(None, root).commands)
            for content in ('[ignore]\n"case.py"=""', 'max-bytes=0', 'unknown=true', 'commands="commit"'):
                config.write_text(content)
                with self.assertRaises(Invalid):
                    load_config(config, root)

    def test_disk_bounds_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'safe.py').write_text('x=1')
            self.assertEqual((1, []), scan(disk_files(root, Config()), Config()))
            (root / 'unsafe.sh').write_text('git init temp')
            self.assertEqual(['unsafe.sh'], scan(disk_files(root, Config()), Config())[1])
            with self.assertRaises(Invalid):
                list(disk_files(root, Config(max_bytes=2)))
            (root / 'link.py').symlink_to(root / 'safe.py')
            with self.assertRaises(Invalid):
                list(disk_files(root, Config()))

    def test_cli_red_then_green_without_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / 'fixture.py'
            sentinel = root / 'executed'
            target.write_text('import subprocess\nsubprocess.run(["git", "init"])\nraise RuntimeError("never run")')
            self.assertEqual(1, main(['--root', str(root)]))
            target.write_text('marker="--local-env-vars"\n' + target.read_text())
            self.assertEqual(0, main(['--root', str(root)]))
            self.assertFalse(sentinel.exists())

    def test_staged_index_and_subdirectory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            # Fixtures always clear the complete hook-local environment before git init.
            env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
            env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
            for name in subprocess.check_output(['git', 'rev-parse', '--local-env-vars'], env=env, text=True).split():
                env.pop(name, None)
            subprocess.run(['git', 'init', '--template=', str(root)], env=env, check=True, capture_output=True)
            (root / 'fixture.py').write_text('run(["git", "init"])')
            subprocess.run(['git', '-C', str(root), 'add', 'fixture.py'], env=env, check=True)
            (root / 'fixture.py').write_text('marker="--local-env-vars"\nrun(["git", "init"])')
            previous = Path.cwd()
            (root / 'nested').mkdir()
            try:
                os.chdir(root / 'nested')
                with patch.dict(os.environ, env, clear=True):
                    self.assertEqual(['fixture.py'], scan(index_files(Config()), Config())[1])
                    self.assertEqual(1, main([]))
            finally:
                os.chdir(previous)
            subprocess.run(['git', '-C', str(root), 'add', 'fixture.py'], env=env, check=True)
            try:
                os.chdir(root)
                with patch.dict(os.environ, env, clear=True):
                    self.assertEqual(0, main([]))
            finally:
                os.chdir(previous)


    def test_index_size_cap_precedes_blob_read(self):
        with patch('git_env_guard.core.git', side_effect=[b'100644 aaaa 0\tfixture.py\0', b'99999999\n']) as plumbing:
            with self.assertRaises(Invalid):
                list(index_files(Config()))
            self.assertEqual(2, plumbing.call_count)

    def test_index_refuses_unmerged_and_symlink(self):
        for entry in (b'100644 aaaa 2\tfixture.py\0', b'120000 aaaa 0\tfixture.py\0'):
            with patch('git_env_guard.core.git', return_value=entry):
                with self.assertRaises(Invalid):
                    list(index_files(Config()))

    def test_docs_and_hook(self):
        root = Path(__file__).resolve().parents[1]
        usage = (root / 'docs/usage.md').read_text()
        for name in ('--root', '--config', '--help', 'extra-globs', 'commands', 'scrub-markers', 'ignore', 'max-bytes'):
            self.assertIn(name, usage)
        self.assertIn('pass_filenames: false', (root / '.pre-commit-hooks.yaml').read_text())


if __name__ == '__main__':
    unittest.main()
