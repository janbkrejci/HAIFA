import unittest

import textstats


class WordsTest(unittest.TestCase):
    def test_lower_cases_and_drops_punctuation(self) -> None:
        self.assertEqual(textstats.words("Hello, world! Hello."), ["hello", "world", "hello"])

    def test_keeps_apostrophes_and_hyphens_inside_words(self) -> None:
        self.assertEqual(textstats.words("don't well-known"), ["don't", "well-known"])

    def test_empty_text_has_no_words(self) -> None:
        self.assertEqual(textstats.words(""), [])


class WordCountTest(unittest.TestCase):
    def test_counts_words(self) -> None:
        self.assertEqual(textstats.word_count("one two  three\nfour"), 4)


class LineCountTest(unittest.TestCase):
    def test_counts_lines(self) -> None:
        self.assertEqual(textstats.line_count("a\nb\nc"), 3)

    def test_trailing_newline_is_not_a_line(self) -> None:
        self.assertEqual(textstats.line_count("a\nb\n"), 2)

    def test_empty_text_has_no_lines(self) -> None:
        self.assertEqual(textstats.line_count(""), 0)


if __name__ == "__main__":
    unittest.main()
