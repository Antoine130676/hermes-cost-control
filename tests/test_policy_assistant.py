import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "examples" / "policy-assistant"))

import assistant  # noqa: E402
import evaluate  # noqa: E402

HERE = ROOT / "examples" / "policy-assistant"
INDEX = assistant.Index(assistant.load_chunks(assistant.DEFAULT_POLICIES))


class ChunkingAndStemming(unittest.TestCase):
    def test_every_policy_section_becomes_a_chunk_with_a_source_and_heading(self):
        chunks = assistant.load_chunks(assistant.DEFAULT_POLICIES)
        self.assertGreaterEqual(len(chunks), 30)
        self.assertTrue(all(c.source.endswith(".md") and c.heading and c.text for c in chunks))
        self.assertEqual({c.source for c in chunks},
                         {"expenses.md", "leave.md", "data-handling.md", "procurement.md", "remote-work.md"})

    def test_stemmer_makes_word_forms_meet(self):
        for group in (("approve", "approves", "approved", "approval"), ("carry", "carried"), ("remote", "remotely"),
                      ("receipt", "receipts"), ("quote", "quotes")):
            self.assertEqual(len({assistant.stem(w) for w in group}), 1, group)


class Privacy(unittest.TestCase):
    def test_personal_data_is_redacted_and_categories_reported(self):
        text = "Mail anna.k@example.com or call +372 5555 1234, my IBAN is EE38 2200 2210 2014 5685, id 38001085718"
        redacted, found = assistant.redact(text)
        for secret in ("anna.k@example.com", "5555 1234", "EE38", "38001085718"):
            self.assertNotIn(secret, redacted)
        # what matters is that nothing sensitive survives; a long id may be labelled "phone" or "number"
        self.assertTrue({"email", "phone", "iban"} <= set(found))
        self.assertGreaterEqual(redacted.count("removed]"), 4)

    def test_audit_log_never_contains_the_question_or_personal_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "audit.jsonl"
            assistant.answer("How much can I spend on a client dinner? I am anna.k@example.com", INDEX, audit_path=log)
            text = log.read_text(encoding="utf-8")
            self.assertNotIn("dinner", text)
            self.assertNotIn("@", text)
            entry = json.loads(text.splitlines()[0])
            self.assertEqual(set(entry), {"ts", "question_hash", "pii_redacted", "status", "sources", "mode"})
            self.assertEqual(entry["pii_redacted"], ["email"])


class Behaviour(unittest.TestCase):
    def test_personal_data_in_a_question_does_not_change_the_answer(self):
        plain = assistant.answer("Who has to sign off an expense claim of 1,500 euros?", INDEX)
        with_pii = assistant.answer("I am anna.k@example.com, who has to sign off an expense claim of 1,500 euros?", INDEX)
        self.assertEqual(with_pii["pii_redacted"], ["email"])
        self.assertEqual(with_pii["status"], plain["status"])
        self.assertEqual(with_pii["sources"][:1], plain["sources"][:1])

    def test_suggestions_show_the_sentence_that_matches_the_question(self):
        res = assistant.answer("Can I fly business class to Singapore?", INDEX)
        top = res["hits"][0][1]
        self.assertIn("Business class", assistant.best_sentence(res["question_redacted"], top))

    def test_a_confident_answer_names_its_source(self):
        res = assistant.answer("How much can I spend on a client dinner?", INDEX)
        self.assertEqual(res["status"], "answered")
        self.assertEqual(res["sources"][0], "expenses.md > Meals and client entertainment")

    def test_questions_the_policies_do_not_cover_never_get_a_confident_answer(self):
        for q in ("What is the capital of France?", "What is the best pizza topping?", "What is the weather tomorrow?",
                  "How do I get a mortgage?", "How do I reset my router password?", "What will our share price be next year?"):
            self.assertNotEqual(assistant.answer(q, INDEX)["status"], "answered", q)

    def test_nothing_matching_is_refused_with_guidance(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assistant.main(["What is the best pizza topping?", "--no-audit"])
        self.assertIn("I can't find this in the policies", buf.getvalue())
        self.assertIn("won't guess", buf.getvalue())

    def test_the_model_prompt_contains_only_the_retrieved_excerpts_and_a_refusal_rule(self):
        res = assistant.answer("How much can I spend on a client dinner?", INDEX)
        prompt = assistant.build_prompt(res["question_redacted"], res["hits"])
        self.assertIn("ONLY the excerpts", prompt)
        self.assertIn("I can't find this in the policies", prompt)
        self.assertIn("40 euros per day", prompt)                    # the relevant excerpt is there
        self.assertNotIn("Payroll records are kept", prompt)         # an unrelated section is not


class Evaluation(unittest.TestCase):
    def test_both_question_sets_meet_their_thresholds(self):
        for name in ("golden", "heldout"):
            summary, _ = evaluate.evaluate(HERE / f"{name}.json")
            t = evaluate.THRESHOLDS[name]
            self.assertGreaterEqual(summary["hit@3"], t["hit@3"], name)
            self.assertGreaterEqual(summary["not_refused"], t["not_refused"], name)
            self.assertLessEqual(summary["wrongly_confident"], t["max_wrongly_confident"], name)


if __name__ == "__main__":
    unittest.main()
