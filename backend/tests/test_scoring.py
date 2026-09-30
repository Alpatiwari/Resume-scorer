"""
Tests for the scoring logic. No database, Redis, Gemini or network needed.

Run from the backend/ folder:
    python -m unittest discover -s tests -t . -v
or, if you have pytest installed:
    pytest -v
"""
import unittest
from unittest import mock

from app.services import nlp_extractor, scorer
from app.services.nlp_extractor import (
    JobRequirements,
    ResumeProfile,
    _find_experience_years_regex,
    _find_skills_regex,
    _split_job_sections,
    extract_job_requirements,
)
from app.services.skill_dictionary import normalize_skill


class SkillMatchingTests(unittest.TestCase):
    def test_go_verb_is_not_the_go_language(self):
        self.assertNotIn("Go", _find_skills_regex("I go beyond expectations and love to go the extra mile."))
        self.assertNotIn("Go", _find_skills_regex("Go beyond the requirements every sprint."))

    def test_go_language_is_found_in_real_contexts(self):
        self.assertIn("Go", _find_skills_regex("Skills: Python, Go, SQL"))
        self.assertIn("Go", _find_skills_regex("Built services in golang"))
        self.assertIn("Go", _find_skills_regex("Languages: Go and Python"))
        self.assertIn("Go", _find_skills_regex("Senior Go developer"))

    def test_excel_verb_is_not_the_spreadsheet(self):
        self.assertNotIn("Excel", _find_skills_regex("I excel at communication."))
        self.assertNotIn("Excel", _find_skills_regex("Excel at stakeholder management."))

    def test_excel_spreadsheet_is_found(self):
        self.assertIn("Excel", _find_skills_regex("Proficient in Excel and Power BI"))
        self.assertIn("Excel", _find_skills_regex("Advanced excel, pivot tables"))

    def test_plain_word_node_is_not_nodejs(self):
        self.assertNotIn("Node.js", _find_skills_regex("Managed a network node inventory."))
        self.assertIn("Node.js", _find_skills_regex("Built APIs with Node.js"))

    def test_case_sensitive_short_aliases(self):
        self.assertIn("JavaScript", _find_skills_regex("Worked with JS and TS daily"))
        self.assertIn("TypeScript", _find_skills_regex("Worked with JS and TS daily"))
        self.assertNotIn("Machine Learning", _find_skills_regex("The ml file was empty"))
        self.assertIn("Machine Learning", _find_skills_regex("Experience with ML pipelines"))

    def test_normalisation_makes_spellings_equal(self):
        self.assertEqual(normalize_skill("React.js"), "React")
        self.assertEqual(normalize_skill("REST API"), "REST APIs")
        self.assertEqual(normalize_skill("Postgres"), "PostgreSQL")
        self.assertEqual(normalize_skill("js"), "JavaScript")
        self.assertEqual(normalize_skill("Some Unknown Tool"), "Some Unknown Tool")


class SkillOverlapTests(unittest.TestCase):
    def test_different_spellings_still_match(self):
        score, matched, missing = scorer._skill_overlap_score(
            ["REST API", "React.js", "Postgres"], ["REST APIs", "React", "PostgreSQL"]
        )
        self.assertEqual(score, 100.0)
        self.assertEqual(missing, [])
        self.assertEqual(len(matched), 3)

    def test_postgres_satisfies_sql_requirement(self):
        score, _, missing = scorer._skill_overlap_score(["PostgreSQL"], ["SQL"])
        self.assertEqual(score, 100.0)
        self.assertEqual(missing, [])

    def test_missing_skills_are_reported(self):
        score, matched, missing = scorer._skill_overlap_score(["Python"], ["Python", "Docker"])
        self.assertEqual(score, 50.0)
        self.assertEqual(matched, ["Python"])
        self.assertEqual(missing, ["Docker"])

    def test_nice_to_have_helps_but_never_counts_as_missing(self):
        with_nice, _, missing_a = scorer._skill_overlap_score(["Python", "Docker"], ["Python"], ["Docker"])
        without_nice, _, missing_b = scorer._skill_overlap_score(["Python"], ["Python"], ["Docker"])
        self.assertEqual(with_nice, 100.0)
        self.assertLess(without_nice, with_nice)
        self.assertEqual(missing_a, [])
        self.assertEqual(missing_b, [])  # not having a nice-to-have is not "missing"

    def test_no_required_skills_means_not_applicable(self):
        self.assertEqual(scorer._skill_overlap_score(["Python"], []), (None, [], []))


class JobDescriptionSplitTests(unittest.TestCase):
    def test_inline_nice_to_have_is_not_required(self):
        with mock.patch.object(nlp_extractor, "_call_llm_json", return_value=(None, "offline")):
            req = extract_job_requirements("Required: Python. Nice to have: Docker, Kubernetes.")
        self.assertEqual(req.required_skills, ["Python"])
        self.assertEqual(sorted(req.nice_to_have_skills), ["Docker", "Kubernetes"])

    def test_heading_sections(self):
        jd = "Requirements:\nPython\nSQL\n\nNice to have:\nDocker\nAWS\n\nResponsibilities:\nBuild APIs with FastAPI"
        required_text, nice_text = _split_job_sections(jd)
        self.assertIn("Python", required_text)
        self.assertIn("FastAPI", required_text)
        self.assertIn("Docker", nice_text)
        self.assertNotIn("Docker", required_text)

    def test_is_a_plus_sentence(self):
        with mock.patch.object(nlp_extractor, "_call_llm_json", return_value=(None, "offline")):
            req = extract_job_requirements("You know Python well. Experience with Docker is a plus.")
        self.assertIn("Python", req.required_skills)
        self.assertNotIn("Docker", req.required_skills)
        self.assertIn("Docker", req.nice_to_have_skills)

    def test_ai_required_skill_that_is_listed_as_nice_is_dropped(self):
        fake = {"required_skills": ["Python", "Docker"], "nice_to_have_skills": [], "min_experience_years": None}
        with mock.patch.object(nlp_extractor, "_call_llm_json", return_value=(fake, None)):
            req = extract_job_requirements("Must know Python.\nNice to have: Docker")
        self.assertNotIn("Docker", req.required_skills)
        self.assertIn("Docker", req.nice_to_have_skills)


class ExperienceYearsTests(unittest.TestCase):
    def test_common_phrasings(self):
        self.assertEqual(_find_experience_years_regex("5 years of experience"), 5.0)
        self.assertEqual(_find_experience_years_regex("5+ years experience in Python"), 5.0)
        self.assertEqual(_find_experience_years_regex("Five years of professional experience"), 5.0)
        self.assertEqual(_find_experience_years_regex("3-5 years of experience"), 3.0)
        self.assertEqual(_find_experience_years_regex("Experience: 4 years"), 4.0)
        self.assertEqual(_find_experience_years_regex("At least 3 years working with APIs"), 3.0)

    def test_no_match(self):
        self.assertIsNone(_find_experience_years_regex("Experience: 2019-2024"))
        self.assertIsNone(_find_experience_years_regex("Fresh graduate"))


class ExperienceScoreTests(unittest.TestCase):
    def test_meets_minimum(self):
        self.assertEqual(scorer._experience_score(6, 5), 100.0)

    def test_below_minimum_scales_down(self):
        self.assertEqual(scorer._experience_score(2, 4), 50.0)

    def test_not_counted_when_unknown(self):
        self.assertIsNone(scorer._experience_score(None, 5))
        self.assertIsNone(scorer._experience_score(3, None))


class FinalScoreTests(unittest.TestCase):
    def _score(self, profile, requirements, embed=60.0, llm=80.0):
        with mock.patch.object(scorer, "semantic_similarity_score", return_value=embed), \
             mock.patch.object(scorer, "llm_judgment_score", return_value={
                 "score": llm, "matched_skills": [], "missing_skills": [], "reasoning": "ok", "error": None}):
            return scorer.score_resume("r1", "some resume text", "some job text", requirements, profile)

    def test_weights_sum_to_one(self):
        from app.config import SCORE_WEIGHTS
        self.assertAlmostEqual(sum(SCORE_WEIGHTS.values()), 1.0)

    def test_more_experience_ranks_higher(self):
        req = JobRequirements(required_skills=["Python"], min_experience_years=5)
        junior = self._score(ResumeProfile(skills=["Python"], experience_years=1), req)
        senior = self._score(ResumeProfile(skills=["Python"], experience_years=6), req)
        self.assertGreater(senior.final_score, junior.final_score)

    def test_unknown_years_adds_warning_and_is_not_punished(self):
        req = JobRequirements(required_skills=["Python"], min_experience_years=5)
        result = self._score(ResumeProfile(skills=["Python"], experience_years=None), req)
        self.assertTrue(any("years" in w for w in result.warnings))

    def test_llm_down_is_flagged_not_faked(self):
        req = JobRequirements(required_skills=["Python"])
        with mock.patch.object(scorer, "semantic_similarity_score", return_value=60.0), \
             mock.patch.object(scorer, "llm_judgment_score", return_value={
                 "score": None, "matched_skills": [], "missing_skills": [], "reasoning": "", "error": "down"}):
            result = scorer.score_resume("r1", "text", "job", req, ResumeProfile(skills=["Python"]))
        self.assertIsNone(result.llm_score)
        self.assertTrue(result.llm_unavailable)
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()