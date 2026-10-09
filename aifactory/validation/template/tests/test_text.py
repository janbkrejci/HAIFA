import unittest

from sandbox import text


class ModuleTest(unittest.TestCase):
    def test_has_a_docstring(self) -> None:
        self.assertTrue(text.__doc__)


@unittest.skipUnless(hasattr(text, "slugify"), "slugify is not there yet (M01-S02-T01)")
class SlugifyTest(unittest.TestCase):
    def test_lowercase_and_hyphens(self) -> None:
        self.assertEqual(text.slugify("Hello World"), "hello-world")

    def test_diacritics_and_punctuation(self) -> None:
        self.assertEqual(text.slugify("Příliš žluťoučký kůň!"), "prilis-zlutoucky-kun")


@unittest.skipUnless(hasattr(text, "truncate"), "truncate is not there yet (M01-S02-T02)")
class TruncateTest(unittest.TestCase):
    def test_short_text_stays(self) -> None:
        self.assertEqual(text.truncate("abc", 5), "abc")

    def test_long_text_gets_an_ellipsis(self) -> None:
        self.assertEqual(text.truncate("abcdef", 4), "abc…")
        self.assertEqual(len(text.truncate("abcdef", 4)), 4)
