#!/usr/bin/env python3
"""Focused tests for group-scoped namelist scalar assignment editing."""
from __future__ import annotations

import unittest

import test_udm_startup_snow_scm as scm


class SetAssignmentTests(unittest.TestCase):
    def test_inserts_when_absent_from_target_group(self) -> None:
        text = "&physics\n history_interval = 30,\n/\n&time_control\n run_minutes = 2,\n/\n"
        got = scm.set_assignment(text, "history_interval", "0", group="time_control")
        self.assertIn("&physics\n history_interval = 30,\n/", got)
        self.assertIn("&time_control\n run_minutes = 2,\n history_interval = 0,\n/", got)

    def test_replaces_only_assignment_in_requested_group(self) -> None:
        text = "&physics\n history_interval = 30,\n/\n&time_control\n history_interval = 15, ! keep\n/\n"
        got = scm.set_assignment(text, "history_interval", "0", group="time_control")
        self.assertIn("&physics\n history_interval = 30,\n/", got)
        self.assertIn("history_interval = 0, ! keep\n", got)
        self.assertNotIn("history_interval = 15, ! keep", got)

    def test_rejects_duplicate_assignment_in_target_group(self) -> None:
        text = "&time_control\n history_interval = 15,\n history_interval = 30,\n/\n"
        with self.assertRaisesRegex(RuntimeError, "duplicate history_interval assignments"):
            scm.set_assignment(text, "history_interval", "0", group="time_control")

    def test_rejects_same_line_duplicate_assignment(self) -> None:
        text = "&time_control\n run_minutes = 1, history_interval = 15, history_interval = 30,\n/\n"
        with self.assertRaisesRegex(RuntimeError, "duplicate history_interval assignments"):
            scm.set_assignment(text, "history_interval", "0", group="time_control")

    def test_replaces_assignment_after_another_same_line_assignment(self) -> None:
        text = "&time_control\n run_minutes = 1, history_interval = 15, frames_per_outfile = 4,\n/\n"
        got = scm.set_assignment(text, "history_interval", "0", group="time_control")
        self.assertIn("run_minutes = 1, history_interval = 0, frames_per_outfile = 4,", got)

    def test_rejects_target_after_whitespace_separated_assignment(self) -> None:
        text = "&time_control\n run_minutes = 1 history_interval = 15,\n/\n"
        with self.assertRaisesRegex(RuntimeError, "unsupported history_interval assignment layout"):
            scm.set_assignment(text, "history_interval", "0", group="time_control")

    def test_rejects_other_assignment_after_target_without_comma(self) -> None:
        text = "&time_control\n history_interval = 1 run_minutes = 2,\n/\n"
        with self.assertRaisesRegex(RuntimeError, "unsupported non-scalar history_interval"):
            scm.set_assignment(text, "history_interval", "0", group="time_control")

    def test_rejects_duplicate_target_without_comma(self) -> None:
        text = "&time_control\n history_interval = 1 history_interval = 2,\n/\n"
        with self.assertRaisesRegex(RuntimeError, "duplicate history_interval assignments"):
            scm.set_assignment(text, "history_interval", "0", group="time_control")

    def test_rejects_duplicate_target_groups(self) -> None:
        text = "&time_control\n run_minutes = 1,\n/\n&time_control\n run_minutes = 2,\n/\n"
        with self.assertRaisesRegex(RuntimeError, "duplicate &time_control blocks"):
            scm.set_assignment(text, "history_interval", "0", group="time_control")

    def test_rejects_indexed_target_instead_of_inserting(self) -> None:
        for lhs in ("ra_lw_physics(1)", "ra_lw_physics ( 1:2 )"):
            with self.subTest(lhs=lhs):
                text = f"&physics\n {lhs} = 4,\n/\n"
                with self.assertRaisesRegex(RuntimeError, "unsupported ra_lw_physics"):
                    scm.set_assignment(text, "ra_lw_physics", "37")

    def test_rejects_bare_and_indexed_duplicate_target(self) -> None:
        text = "&physics\n ra_lw_physics=4, ra_lw_physics(1)=5,\n/\n"
        with self.assertRaisesRegex(RuntimeError, "duplicate ra_lw_physics"):
            scm.set_assignment(text, "ra_lw_physics", "37")

    def test_rejects_same_line_rhs_list(self) -> None:
        for rhs in ("4,5,", "4, 'other',", "4, , 5,", "4,,", "4, , ra_sw_physics=4,"):
            with self.subTest(rhs=rhs):
                with self.assertRaisesRegex(RuntimeError, "unsupported multiple ra_lw_physics"):
                    scm.set_assignment(f"&physics\n ra_lw_physics={rhs}\n/\n", "ra_lw_physics", "37")

    def test_rejects_continued_rhs_list(self) -> None:
        text = "&physics\n ra_lw_physics=4, ! comment\n ! comment line\n 5,\n/\n"
        with self.assertRaisesRegex(RuntimeError, "unsupported continued ra_lw_physics"):
            scm.set_assignment(text, "ra_lw_physics", "37")

    def test_rejects_repeat_and_continued_quoted_rhs(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unsupported repeated ra_lw_physics"):
            scm.set_assignment("&physics\n ra_lw_physics=2*4,\n/\n", "ra_lw_physics", "37")
        with self.assertRaisesRegex(RuntimeError, "unsupported continued quoted run_label"):
            scm.set_assignment("&physics\n run_label='part\n two',\n/\n", "run_label", "'new'")

    def test_preserves_scalar_before_other_assignment_and_comment_lines(self) -> None:
        text = "&physics\n ra_lw_physics=4, ! tail\n ! separate comment\n ra_sw_physics(1)=4,\n/\n"
        got = scm.set_assignment(text, "ra_lw_physics", "37")
        self.assertEqual(got, text.replace("ra_lw_physics=4", "ra_lw_physics=37"))

    def test_actual_scm_fixture_stays_compatible(self) -> None:
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        for lw, sw in ((4, 4), (37, 37)):
            with self.subTest(lw=lw):
                text = scm.make_namelist(root, lw, sw)
                self.assertRegex(text, rf"(?m)^\s*ra_lw_physics\s*=\s*{lw}\s*,")
                self.assertRegex(text, rf"(?m)^\s*ra_sw_physics\s*=\s*{sw}\s*,")
                self.assertIn("history_interval_s = 60,", text)
                self.assertRegex(text, r"(?m)^\s*history_interval\s*=\s*0\s*,")
                self.assertRegex(text, r"(?m)^\s*frames_per_outfile\s*=\s*10000\s*,")

    def test_ignores_comments_and_preserves_quoted_slash_or_bang(self) -> None:
        text = (
            "&physics\n title = 'literal / ! token', note='it''s safe',\n/\n"
            "&time_control\n ! history_interval = 30,\n run_minutes = 1,\n/\n"
        )
        got = scm.set_assignment(text, "history_interval", "0", group="time_control")
        self.assertIn("title = 'literal / ! token',", got)
        self.assertIn("note='it''s safe'", got)
        self.assertIn("! history_interval = 30,", got)
        self.assertIn("history_interval = 0,", got)

    def test_quoted_target_looking_text_is_not_an_assignment(self) -> None:
        text = '&time_control\n title = "history_interval = 90, ! /",\n/\n'
        got = scm.set_assignment(text, "history_interval", "0", group="time_control")
        self.assertIn('title = "history_interval = 90, ! /",', got)
        self.assertIn("history_interval = 0,", got)

    def test_replaces_quoted_scalar_and_scalar_without_trailing_comma(self) -> None:
        quoted = "&physics\n run_label = 'old, ! label',\n/\n"
        got_quoted = scm.set_assignment(quoted, "run_label", "'new, ! label'")
        self.assertIn("run_label = 'new, ! label',", got_quoted)
        quoted_equals = "&physics\n run_label = 'old=label',\n/\n"
        got_equals = scm.set_assignment(quoted_equals, "run_label", "'new=label'")
        self.assertIn("run_label = 'new=label',", got_equals)
        no_comma = "&time_control\n history_interval = 15 ! tail\n/\n"
        got_no_comma = scm.set_assignment(no_comma, "history_interval", "0", group="time_control")
        self.assertIn("history_interval = 0 ! tail\n", got_no_comma)

    def test_crlf_is_preserved_without_duplicate_carriage_returns(self) -> None:
        text = "&time_control\r\nhistory_interval = 15, ! old\r\n/\r\n"
        replaced = scm.set_assignment(text, "history_interval", "0", group="time_control")
        inserted = scm.set_assignment("&time_control\r\nrun_minutes = 1,\r\n/\r\n",
                                      "history_interval", "0", group="time_control")
        self.assertIn("history_interval = 0, ! old\r\n", replaced)
        self.assertNotIn("\r\r\n", replaced)
        self.assertIn("history_interval = 0,\r\n/\r\n", inserted)
        self.assertNotIn("\r\r\n", inserted)

    def test_rejects_empty_rhs(self) -> None:
        text = "&time_control\n history_interval = ,\n/\n"
        with self.assertRaisesRegex(RuntimeError, "empty history_interval"):
            scm.set_assignment(text, "history_interval", "0", group="time_control")

    def test_missing_and_unterminated_group_reject(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "missing &time_control"):
            scm.set_assignment("&physics\n/\n", "history_interval", "0", group="time_control")
        with self.assertRaisesRegex(RuntimeError, "unterminated &time_control"):
            scm.set_assignment("&time_control\n run_minutes = 1,\n&physics\n/\n",
                               "history_interval", "0", group="time_control")


if __name__ == "__main__":
    unittest.main()
