import pytest

from app.keywords import analyze_keywords, coverage_report
from app.latex_edit import apply_changes, editable_spans, validate_change
from app.models import LatexChange
from app import rewrite

# The technical requirements and responsibilities from the user's Atlassian JD.
JD = """Build highly scalable backend applications in a cross-geo distributed environment.
Review code for readability, testing patterns, documentation, reliability, security and performance.
Mentor teammates. Ensure full visibility, error reporting, and monitoring of backend services.
Participate in Agile development including sprint planning and retrospectives.
Experience with performant RESTful micro-services and modern object-oriented programming:
Java, Kotlin, Go, Scala, Python. Database technology: RDBMS like Oracle or Postgres
and/or NoSQL like DynamoDB or Cassandra. SaaS, PaaS, IaaS and public cloud (AWS, GAE, Azure).
Familiarity with cloud architecture patterns."""


@pytest.fixture
def source():
    return r'''\documentclass{article}
\newcommand{\resumeItem}[1]{\item #1}
\begin{document}
\section{Experience}
\begin{itemize}
\resumeItem{Designed scalable SaaS integrations with REST APIs and microservices for Workday and Oracle HCM to support reliable data ingestion.}
\resumeItem{Built backend services with AWS and DynamoDB for internal reporting and reliable distributed workflows.}
\end{itemize}
\section{Technical Skills}
\textbf{Databases}{: MongoDB, DynamoDB, RDS, SQL}
\textbf{Languages}{: Go, Java, Python}
\textbf{Tools}{: AWS, CloudWatch, GraphQL (familiar)}
\section{Education}
Computer Science degree, Example University.
\end{document}'''


def as_map(report):
    return {item['keyword']: item for item in report}


def test_atlassian_keywords_distinguish_supported_categories_from_missing_tools(source):
    report = as_map(analyze_keywords(source, JD))
    assert report['NoSQL']['status'] == 'supported'
    assert report['NoSQL']['evidence'] in {'MongoDB', 'DynamoDB'}
    assert report['RDBMS']['status'] == 'supported'
    assert report['RESTful micro-services']['status'] == 'supported'
    assert report['public cloud']['status'] == 'supported'
    assert report['monitoring']['status'] == 'supported'
    for term in ('PostgreSQL', 'Oracle', 'Cassandra', 'Azure', 'GAE', 'PaaS', 'IaaS', 'Kotlin', 'Scala', 'mentoring', 'testing', 'code reviews'):
        assert report[term]['status'] == 'missing', term
    for term in ('AWS', 'DynamoDB', 'Java', 'Go', 'Python', 'SaaS'):
        assert report[term]['status'] == 'present', term


def test_sql_does_not_imply_postgres_or_specific_vendor():
    report = as_map(analyze_keywords(r'\begin{document}Developed SQL reporting scripts.\end{document}', JD))
    assert report['PostgreSQL']['status'] == 'missing'
    assert report['Oracle']['status'] == 'missing'
    assert report['RDBMS']['status'] == 'missing'


def test_comments_preamble_urls_and_macro_names_are_not_skill_evidence():
    source = r'''\newcommand{\PostgreSQL}{PostgreSQL}
% NoSQL, DynamoDB, Cassandra
\begin{document}
% Experience using PostgreSQL, Azure, Java.
\href{https://example.com/PostgreSQL/DynamoDB}{My profile}
\input{PostgreSQL}
Built reporting tools using Python.
\end{document}'''
    report = as_map(analyze_keywords(source, JD))
    for term in ('PostgreSQL', 'NoSQL', 'DynamoDB', 'Azure', 'Java', 'Cassandra'):
        assert report[term]['status'] == 'missing', term
    assert report['Python']['status'] == 'present'


def test_no_substring_matches_for_java_or_sql():
    source = r'\begin{document}JavaScript, NoSQL databases with DynamoDB.\end{document}'
    report = as_map(analyze_keywords(source, JD + " Java and SQL."))
    assert report['Java']['status'] == 'missing'
    assert report['SQL']['status'] == 'missing'


def test_existing_skill_lists_can_gain_nosql_without_changing_design(source):
    span = next(s for s in editable_spans(source) if s.kind == 'skills' and 'MongoDB' in s.text)
    after = span.text.replace('MongoDB, DynamoDB', 'NoSQL databases (MongoDB, DynamoDB)')
    change = LatexChange(id=span.id, before=span.text, after=after)
    result = apply_changes(source, [change])
    assert result == source[:span.start] + after + source[span.end:]
    assert r'\textbf{Databases}' in result
    assert 'GraphQL (familiar)' in result
    assert 'Computer Science degree' in result


def test_nosql_is_allowed_with_bullet_local_evidence():
    before = 'Built backend services with DynamoDB for internal reporting and reliable distributed workflows.'
    after = before.replace('DynamoDB', 'DynamoDB, a NoSQL database,')
    validate_change(before, after)


@pytest.mark.parametrize('technology', ['PostgreSQL', 'postgres', 'Azure', 'Cassandra', 'Kubernetes', 'PaaS', 'IaaS'])
def test_unknown_technology_cannot_be_inserted_even_in_lowercase(technology):
    before = 'Built backend services with DynamoDB for internal reporting and reliable distributed workflows.'
    after = before.replace('DynamoDB', 'DynamoDB and ' + technology)
    with pytest.raises(ValueError, match='support'):
        validate_change(before, after)


def test_tools_cannot_be_borrowed_from_another_role(source):
    span = next(s for s in editable_spans(source) if 'Workday' in s.text)
    after = span.text.replace('REST APIs', 'REST APIs with DynamoDB')
    with pytest.raises(ValueError, match='DynamoDB'):
        apply_changes(source, [LatexChange(id=span.id, before=span.text, after=after)])


def test_true_postgres_alias_is_allowed_but_not_invented():
    before = 'Built backend services with Postgres for internal reporting and reliable distributed workflows.'
    after = before.replace('Postgres', 'PostgreSQL')
    validate_change(before, after)


def test_coverage_is_based_on_edited_source_not_model_claims(source):
    report = analyze_keywords(source, JD)
    original = as_map(coverage_report(report, source, source))
    assert not original['NoSQL']['added']
    assert not original['NoSQL']['in_output']
    assert original['AWS']['in_output']
    span = next(s for s in editable_spans(source) if s.kind == 'skills' and 'MongoDB' in s.text)
    change = LatexChange(id=span.id, before=span.text, after=span.text.replace('MongoDB, DynamoDB', 'NoSQL databases (MongoDB, DynamoDB)'))
    result = apply_changes(source, [change])
    edited = as_map(coverage_report(report, source, result))
    assert edited['NoSQL']['added'] and edited['NoSQL']['in_output']
    assert not edited['PostgreSQL']['added'] and not edited['PostgreSQL']['in_output']


def test_model_gets_supported_targets_and_returns_verified_keywords(source, monkeypatch):
    span = next(s for s in editable_spans(source) if s.kind == 'skills' and 'MongoDB' in s.text)
    change = LatexChange(id=span.id, before=span.text, after=span.text.replace('MongoDB, DynamoDB', 'NoSQL databases (MongoDB, DynamoDB)'), keywords_added=['PostgreSQL'])
    seen = []
    def generate(system, user):
        seen.append((system, user))
        return {'changes': [change.model_dump()]}, 'test-model'
    monkeypatch.setattr(rewrite, '_generate_json', generate)
    proposal = rewrite.propose_latex(source, "NoSQL databases like DynamoDB and Postgres are relevant to this role.")
    assert len(proposal.changes) == 1
    assert proposal.changes[0].keywords_added == ['NoSQL']
    report = {item.keyword: item for item in proposal.keyword_report}
    assert report['NoSQL'].added
    assert not report['PostgreSQL'].added
    assert 'keyword_analysis' in seen[0][1] and 'MongoDB' in seen[0][1]
    assert 'Prioritize supported terms' in seen[0][0]


def test_supported_categories_are_suggested_even_if_model_returns_no_edits(source, monkeypatch):
    monkeypatch.setattr(rewrite, '_generate_json', lambda *a: ({'changes': [], 'notes': 'No wording changes needed.'}, 'test-model'))
    proposal = rewrite.propose_latex(source, JD)
    assert proposal.changes
    edited = apply_changes(source, proposal.changes)
    assert 'MongoDB (NoSQL)' in edited or 'DynamoDB (NoSQL)' in edited
    for phrase in ('RDS (RDBMS)', 'AWS (public cloud)', 'CloudWatch (monitoring)'):
        assert phrase in edited
    assert 'PostgreSQL' not in edited and 'Cassandra' not in edited and 'Azure' not in edited
    assert 'GraphQL (familiar)' in edited
    assert edited.count(r'\resumeItem{') == source.count(r'\resumeItem{')
    report = {item.keyword: item for item in proposal.keyword_report}
    assert report['NoSQL'].added and report['public cloud'].added


def test_keyword_fallback_merges_with_model_changes_without_duplicate_ids(source, monkeypatch):
    span = next(s for s in editable_spans(source) if s.kind == 'skills' and 'MongoDB' in s.text)
    change = LatexChange(id=span.id, before=span.text, after=span.text.replace('MongoDB', 'MongoDB (NoSQL)'))
    monkeypatch.setattr(rewrite, '_generate_json', lambda *a: ({'changes': [change.model_dump()]}, 'test-model'))
    proposal = rewrite.propose_latex(source, JD)
    ids = [item.id for item in proposal.changes]
    assert len(ids) == len(set(ids))
    edited = apply_changes(source, proposal.changes)
    assert edited.count('(NoSQL)') == 1
    assert 'RDS (RDBMS)' in edited


def test_skill_expansion_never_edits_link_targets_labels_or_math():
    source = r'''\begin{document}
\section{Technical Skills}
\href{https://example.com/MongoDB,DynamoDB}{MongoDB, DynamoDB}
\(\text{MongoDB, DynamoDB}\)
\textbf{Databases}{: MongoDB, DynamoDB}
\end{document}'''
    spans = editable_spans(source)
    assert len(spans) == 1
    assert spans[0].text == ': MongoDB, DynamoDB'
    assert spans[0].kind == 'skills'


def test_short_nosql_annotation_preserves_source_names_and_familiarity():
    source = r'\begin{document}\section{Technical Skills}\textbf{Databases}{: MongoDB, DynamoDB}\end{document}'
    span = editable_spans(source)[0]
    after = span.text.replace('MongoDB', 'MongoDB (NoSQL)')
    result = apply_changes(source, [LatexChange(id=span.id, before=span.text, after=after)])
    assert result == source.replace(span.text, after)


def test_every_category_keyword_subset_is_valid_and_keeps_original_tools(source, monkeypatch):
    monkeypatch.setattr(rewrite, '_generate_json', lambda *a: ({'changes': []}, 'test-model'))
    proposal = rewrite.propose_latex(source, JD)
    db_change = next(change for change in proposal.changes if 'NoSQL' in change.keywords_added)
    assert set(db_change.keywords_added) == {'NoSQL', 'RDBMS'}
    assert len(db_change.keyword_variants) == 4
    for variant in db_change.keyword_variants:
        edited = apply_changes(source, [db_change.model_copy(update={'after': variant.after})])
        assert ('NoSQL' in edited) == ('NoSQL' in variant.keywords)
        assert ('RDBMS' in edited) == ('RDBMS' in variant.keywords)
        assert 'MongoDB' in edited and 'DynamoDB' in edited and 'RDS' in edited
        assert 'GraphQL (familiar)' in edited
    empty = next(variant for variant in db_change.keyword_variants if not variant.keywords)
    assert empty.after == db_change.before


def test_cloud_and_monitoring_are_independently_selectable(source, monkeypatch):
    monkeypatch.setattr(rewrite, '_generate_json', lambda *a: ({'changes': []}, 'test-model'))
    proposal = rewrite.propose_latex(source, JD)
    change = next(change for change in proposal.changes if 'public cloud' in change.keywords_added)
    assert set(change.keywords_added) == {'public cloud', 'monitoring'}
    cloud_only = next(variant for variant in change.keyword_variants if variant.keywords == ['public cloud'])
    edited = apply_changes(source, [change.model_copy(update={'after': cloud_only.after})])
    assert 'AWS (public cloud)' in edited
    assert 'CloudWatch (monitoring)' not in edited
    assert 'CloudWatch' in edited


def test_model_supplied_variants_are_not_trusted(source, monkeypatch):
    span = next(span for span in editable_spans(source) if span.kind == 'skills' and 'MongoDB' in span.text)
    raw = {'id': span.id, 'before': span.text, 'after': span.text.replace('MongoDB', 'MongoDB (NoSQL)'),
           'keyword_variants': [{'keywords': ['NoSQL'], 'after': span.text + ', PostgreSQL'}]}
    monkeypatch.setattr(rewrite, '_generate_json', lambda *a: ({'changes': [raw]}, 'test-model'))
    proposal = rewrite.propose_latex(source, 'Experience with NoSQL databases such as MongoDB is relevant to this backend job.')
    change = next(change for change in proposal.changes if 'NoSQL' in change.keywords_added)
    assert change.keyword_variants
    assert all('PostgreSQL' not in variant.after for variant in change.keyword_variants)


def test_explicit_new_skill_selection_changes_skills_only(source):
    from app.keywords import add_selected_skills
    edited, additions = add_selected_skills(source, ['PostgreSQL', 'Azure'])
    assert additions == ['PostgreSQL', 'Azure']
    assert 'PostgreSQL' in edited and 'Azure' in edited
    assert source.split(r'\section{Technical Skills}')[0] == edited.split(r'\section{Technical Skills}')[0]
    assert r'\textbf{Databases}{: MongoDB, DynamoDB, RDS, SQL, PostgreSQL}' in edited
    assert r'\textbf{Tools}{: AWS, CloudWatch, GraphQL (familiar), Azure}' in edited


def test_new_skills_are_never_added_without_selection(source):
    from app.keywords import add_selected_skills
    assert add_selected_skills(source, []) == (source, [])


def test_skill_insertion_deduplicates_and_escapes_tex(source):
    from app.keywords import add_selected_skills
    edited, added = add_selected_skills(source, ['PostgreSQL', 'PostgreSQL', 'Python', 'C#'])
    assert added == ['PostgreSQL', 'C#']
    assert edited.count('PostgreSQL') == 1
    assert r'C\#' in edited
    assert add_selected_skills(edited, ['PostgreSQL', 'C#']) == (edited, [])


@pytest.mark.parametrize('term', [r'\input{/etc/passwd}', 'Postgres; rm', 'unknown-skill'])
def test_only_catalog_terms_can_be_inserted_as_new_skills(source, term):
    from app.keywords import add_selected_skills
    with pytest.raises(ValueError, match='Choose keywords'):
        add_selected_skills(source, [term])


def test_no_skills_slot_has_actionable_error():
    from app.keywords import add_selected_skills
    source = r'\begin{document}\resumeItem{Built reliable internal dashboards using Python and SQL to support operations teams.}\end{document}'
    with pytest.raises(ValueError, match='skills list'):
        add_selected_skills(source, ['PostgreSQL'])


@pytest.mark.parametrize('error', [rewrite.ModelResponseError('truncated', 'incomplete'), rewrite.ModelResponseError('invalid_json', 'invalid'), RuntimeError('unavailable')])
def test_keyword_selection_survives_ai_failure(source, monkeypatch, error):
    def failed(*args):
        raise error
    monkeypatch.setattr(rewrite, '_generate_json', failed)
    result = rewrite.propose_latex(source, JD)
    assert result.ai_status == 'unavailable'
    assert 'Keyword matching is still available' in result.ai_warning
    assert not result.model_used
    assert result.keyword_report
    assert any('NoSQL' in change.keywords_added for change in result.changes)
    assert 'PostgreSQL' not in apply_changes(source, result.changes)


def test_invalid_model_shape_does_not_block_keyword_workflow(source, monkeypatch):
    monkeypatch.setattr(rewrite, '_generate_json', lambda *a: ({'wrong_key': []}, 'test'))
    result = rewrite.propose_latex(source, JD)
    assert result.ai_status == 'unavailable'
    assert result.keyword_report
    assert any(item.keyword == 'PostgreSQL' for item in result.keyword_report)
