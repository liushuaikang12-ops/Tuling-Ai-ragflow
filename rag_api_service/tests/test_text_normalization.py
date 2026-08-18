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

    def test_does_not_treat_equation_reference_parameters_as_formula(self) -> None:
        source = "其中对(1.1)取N=1，α=1，β=-2，a_1=1，b_1=3。"

        result = standardize_formula_markdown(source)

        self.assertFalse(result.changed)
        self.assertFalse(result.needs_visual_review)

    def test_standard_display_math_is_idempotent(self) -> None:
        source = "\\[x = \\frac{a}{b}\\tag{2.1}\\]"

        result = standardize_formula_markdown(source)

        self.assertFalse(result.changed)
        self.assertEqual(result.content, source)
        self.assertEqual(result.equation_labels, ("2.1",))

    def test_annotated_formula_ignores_references_in_original_context(self) -> None:
        source = (
            "# 原文公式：色散关系\n"
            "- 公式编号：(1.2)\n"
            "- 原文上下文：在式(1.1)中参数为任意复数\n\n"
            "\\[a_s^2=0\\tag{1.2}\\]"
        )

        result = standardize_formula_markdown(source)

        self.assertEqual(result.equation_labels, ("1.2",))

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

    def test_exact_formula_tag_outranks_context_reference(self) -> None:
        exact = {"content": "\\[x=1\\tag{1.1}\\]"}
        explanation = {
            "content": "在式(1.1)中参数如下 " + "\\frac{x}{y}=1 " * 20
        }

        self.assertGreater(
            RAGFlowBackend._formula_score(exact, ["1.1"]),
            RAGFlowBackend._formula_score(explanation, ["1.1"]),
        )

    def test_parses_formula_vision_json_and_builds_searchable_chunk(self) -> None:
        parsed = RAGFlowBackend._parse_formula_vision(
            '{"equation_number":"1.2","latex":"a_s^2=0",'
            '"formula_name":"Ito 方程 N-孤子解的色散关系",'
            '"description":"给出参数约束","confidence":0.98}',
            "1.2",
        )
        content = RAGFlowBackend._formula_chunk_content(
            latex=parsed["latex"],
            label=parsed["equation_number"],
            name=parsed["formula_name"],
            description=parsed["description"],
            document_name="论文.pdf",
            page=7,
        )

        self.assertIn("# 原文公式：Ito 方程 N-孤子解的色散关系", content)
        self.assertIn("- 公式编号：(1.2)", content)
        self.assertIn("- 原文 PDF 页码：7", content)
        self.assertIn("- 原文上下文：给出参数约束", content)
        self.assertIn("\\[\na_s^2=0\n\\tag{1.2}\n\\]", content)

    def test_repairs_unescaped_latex_in_vision_json(self) -> None:
        parsed = RAGFlowBackend._parse_formula_vision(
            '{"equation_number":"1.2","latex":"a_s^2 + \\alpha=0",'
            '"formula_name":"色散关系","confidence":1}',
            "1.2",
        )

        self.assertEqual(parsed["latex"], "a_s^2 + \\alpha=0")

    def test_preserves_json_control_like_latex_commands(self) -> None:
        parsed = RAGFlowBackend._parse_formula_vision(
            '{"equation_number":"1.2","latex":"\\beta+\\tau+\\frac{a}{b}=0",'
            '"confidence":1}',
            "1.2",
        )

        self.assertEqual(parsed["latex"], "\\beta+\\tau+\\frac{a}{b}=0")

    def test_derives_formula_name_from_original_context(self) -> None:
        context = (
            "(2+1)维Ito方程的N-孤子解的方程表达式如下，"
            "其中色散关系如下。"
        )

        self.assertEqual(
            RAGFlowBackend._formula_name_from_context("1.1", context),
            "(2+1)维Ito方程的N-孤子解的方程表达式",
        )
        self.assertEqual(
            RAGFlowBackend._formula_name_from_context("1.2", context),
            "(2+1)维Ito方程的N-孤子解的色散关系",
        )

    def test_parses_python_raw_latex_string(self) -> None:
        parsed = RAGFlowBackend._parse_formula_vision(
            '{"equation_number":"1.6","latex": r"\\begin{cases}f=1\\end{cases}",'
            '"confidence":0.98}',
            "1.6",
        )

        self.assertEqual(parsed["latex"], "\\begin{cases}f=1\\end{cases}")

    def test_selects_expected_formula_from_vision_array(self) -> None:
        parsed = RAGFlowBackend._parse_formula_vision(
            '[{"equation_number":"2.1","latex":"x=1","confidence":1},'
            '{"equation_number":"2.3","latex":"\\omega^2-k^2=0",'
            '"confidence":1}]',
            "2.3",
        )

        self.assertEqual(parsed["equation_number"], "2.3")
        self.assertEqual(parsed["latex"], "\\omega^2-k^2=0")

    def test_accepts_asymptotic_formula_relation(self) -> None:
        parsed = RAGFlowBackend._parse_formula_vision(
            '{"equation_number":"2.20","latex":"f_2 \\sim x^2",'
            '"confidence":1}',
            "2.20",
        )

        self.assertEqual(parsed["latex"], "f_2 \\sim x^2")


if __name__ == "__main__":
    unittest.main()
