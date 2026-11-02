from itch_finder.__main__ import main
from itch_finder.jobs import blockers_by_ad, needs, parse_ads, phrases, render

DASHED = """AI Engineer
Build production AI agents on Azure OpenAI. Hybrid.
https://example.com/job/1
---
Senior AI Engineer
Agentic AI and RAG over company documents. Evaluation of LLM outputs.
Recruited by
Jane Recruiter
---
Computer Vision Engineer
C++ perception for autonomous platforms. Active NV1 security clearance required.
"""

RESULTS_PAGE = """Perform a job search
ai engineer jobs 269 jobs
Listed twelve hours ago
AI Engineer
at
Acme
Production AI agents for business workflows
Listed three days ago
Associate AI Engineer
at
Beta Co
Automate workflows with AI agents
"""


def test_parse_dashed_ads_keeps_titles_urls_and_drops_recruiter_names():
    ads = parse_ads(DASHED, "ads")
    assert [a.title for a in ads] == ["AI Engineer", "Senior AI Engineer", "Computer Vision Engineer"]
    assert ads[0].url == "https://example.com/job/1"
    assert ads[0].post_id == "ads#1"
    assert "Jane Recruiter" not in ads[1].body
    assert "Recruited by" not in ads[1].body


def test_parse_results_page_splits_on_listed_lines_and_drops_page_header():
    ads = parse_ads(RESULTS_PAGE, "seek")
    assert [a.title for a in ads] == ["AI Engineer", "Associate AI Engineer"]
    assert all("Perform a job search" not in a.text for a in ads)


def test_parse_ignores_empty_chunks():
    assert parse_ads("\n---\n\n---\n", "x") == []


def test_needs_counts_ads_and_flags_what_is_deliverable():
    ordered = needs(parse_ads(DASHED, "ads"))
    rows = {r["need"]: r for r in ordered}
    assert ordered[0]["need"] == "AI agents"
    assert rows["AI agents"]["ads"] == 2
    assert rows["AI agents"]["deliverable"] is True
    assert rows["Computer vision"]["ads"] == 1
    assert rows["Computer vision"]["deliverable"] is False
    assert "Model training / fine-tuning" not in rows


def test_blockers_count_hiring_only_requirements():
    counts = blockers_by_ad(parse_ads(DASHED, "ads"))
    assert counts["Security clearance"] == 1
    assert "On-site days" not in counts


def test_phrases_need_two_ads_and_skip_niche_words():
    top = dict(phrases(parse_ads(RESULTS_PAGE, "seek"), frozenset({"ai", "engineer"})))
    assert top["agent"] == 2
    assert top["workflow"] == 2
    assert "engineer" not in top
    assert "acme" not in top


def test_render_has_needs_table_blockers_and_offer_for_top_deliverable_need():
    ads = parse_ads(DASHED, "ads")
    md = render("ai engineer", "2026-11-02", ads, frozenset({"ai", "engineer"}))
    assert "# Job-ad needs: ai engineer (2026-11-02)" in md
    assert "| AI agents | 2 | 67% | yes |" in md
    assert "| Computer vision | 1 | 33% | no |" in md
    assert "Security clearance: 1 of 3 ads" in md
    assert "## Draft offers: AI agents" in md
    assert "Jane Recruiter" not in md


def test_cli_jobs_reads_pasted_files_and_writes_report(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ads.txt").write_text(DASHED, encoding="utf-8")
    assert main(["jobs", "ads.txt", "--niche", "ai engineer"]) == 0
    reports = list((tmp_path / "itch_reports").glob("jobs-ai-engineer-*.md"))
    assert len(reports) == 1
    out = capsys.readouterr().out
    assert "3 ads" in out
    assert "AI agents" in out


def test_cli_jobs_missing_file_is_a_clear_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["jobs", "nope.txt", "--niche", "ai engineer"]) == 2
    assert "nope.txt" in capsys.readouterr().err
