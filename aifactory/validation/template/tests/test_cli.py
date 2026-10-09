import io
import unittest
from contextlib import redirect_stdout

import sandbox
from sandbox import cli, text


def _run(*args: str) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(list(args))
    return code, out.getvalue().strip()


class MainTest(unittest.TestCase):
    def test_no_arguments(self) -> None:
        self.assertEqual(cli.main([]), 0)


@unittest.skipUnless(hasattr(sandbox, "__version__"), "--version is not there yet (M02-S01-T02)")
class VersionTest(unittest.TestCase):
    def test_version(self) -> None:
        self.assertEqual(_run("--version"), (0, sandbox.__version__))


@unittest.skipUnless(hasattr(cli, "greet"), "greet is not there yet (M02-S01-T01)")
class GreetTest(unittest.TestCase):
    def test_greet(self) -> None:
        expected = f"Hello, {text.slugify('Jan Novák')}!"
        self.assertEqual(cli.greet("Jan Novák"), expected)
        self.assertEqual(_run("greet", "Jan Novák"), (0, expected))
