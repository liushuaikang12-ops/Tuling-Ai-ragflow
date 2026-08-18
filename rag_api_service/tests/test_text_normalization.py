from __future__ import annotations

import unittest

from core.text_normalization import standardize_formula_markdown
from core.backends.ragflow import RAGFlowBackend


class FormulaMarkdownNormalizationTest(unittest.TestCase):
    def test_converts_latex_and_removes_flattened_duplicate(self) -> None:
        source = (
            "u = 2(ln f)_{xx}, f = \\sum_{j=1}^N \\exp(\\tau_j)\n"
            "e^{A_{js}} = \\frac{a_j-a_s}{a_j+a_s\n"
            "(1.1)(1.1)\n"
            "{u=2(ln f)xx, f=exp(Nμjτj)}"
        )

        result = standardize_formula_markdown(source)

        self.assertTrue(result.changed)
        self.assertEqual(result.equation_labels, ("1.1",))
        self.assertTrue(result.content.startswith("\\["))
        self.assertIn("\\begin{aligned}", result.content)
        self.assertIn("\\tag{1.1}", result.content)
        self.assertIn("\\ln f", result.content)
        self.assertNotIn("(1.1)(1.1)", result.content)
        self.assertEqual(result.content.count("{"), result.content.count("}"))

    def test_marks_flattened_formula_for_visual_review_without_rewriting(self) -> None:
        source = "(1.2) a s 4 c s + αa s 2 b s c s + βa s 2 c s = 0, s = 1"

        result = standardize_formula_markdown(source)

        self.assertFalse(result.changed)
        self.assertTrue(result.needs_visual_review)
        self.assertEqual(result.content, source)

    def test_does_not_mark_explanatory_prose_as_formula(self) -> None:
        source = "在方程(1.1)中这些参数为任意复数，下面说明这个公式的物理意义。" * 4

        result = standardize_formula_markdown(source)

        self.assertFalse(result.changed)
        self.assertFalse(result.needs_visual_review)

    def test_standard_display_math_is_idempotent(self) -> None:
        source = "\\[x = \\frac{a}{b}\\tag{2.1}\\]"

        result = standardize_formula_markdown(source)

        self.assertFalse(result.changed)
        self.assertEqual(result.content, source)
        self.assertEqual(result.equation_labels, ("2.1",))

    def test_formula_questions_only_use_local_equation_context(self) -> None:
        chunks = [
            {
                "content": (
                    "(2+1)维Ito方程的N-孤子解的方程表达式如下[12]\n"
                    "在式(1.1)中参数为任意复数。\n"
                    + ("后续章节的普通说明。" * 40)
                    + "图1-3：不同角度Ito方程双孤子解图像"
                )
            }
        ]

        questions = RAGFlowBackend._formula_questions(("1.1",), chunks)

        self.assertEqual(
            questions,
            [
                "方程(1.1)的完整 LaTeX 公式是什么？",
                "(2+1)维Ito方程的N-孤子解的方程表达式是什么？",
            ],
        )


if __name__ == "__main__":
    unittest.main()
