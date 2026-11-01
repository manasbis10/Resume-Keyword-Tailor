"""Synthetic keyword insertion smoke test; only the model response is mocked.

Run: python -m tests.browser_keywords http://127.0.0.1:8000
"""
import base64
import sys
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright
from pypdf import PdfReader

from app.latex_build import compile_latex
from app.latex_edit import editable_spans
from app.latex_preview import preview_pages
from app.models import LatexChange
from app.rewrite import ModelResponseError, propose_latex


def run():
    base_url = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'
    source = Path('examples/resume.tex').read_text().replace('Python, SQL, Kafka, GraphQL (familiar), Git', 'Python, SQL, DynamoDB, MongoDB, AWS, GraphQL (familiar), Git')
    span = next(s for s in editable_spans(source) if s.kind == 'skills')
    after = span.text.replace('DynamoDB, MongoDB', 'NoSQL databases (DynamoDB, MongoDB)').replace('AWS', 'AWS (public cloud)')
    change = LatexChange(id=span.id, before=span.text, after=after, reason='Use supported database and cloud category keywords from the job posting.')
    job = 'Backend engineer building reliable services with Python, SQL, NoSQL like DynamoDB or Cassandra, RDBMS like Postgres, and public cloud offerings such as AWS and Azure.'
    with patch('app.rewrite._generate_json', return_value=({'changes': [change.model_dump()]}, 'test-model')):
        proposal = propose_latex(source, job).model_dump()
    assert len(proposal['changes']) == 1
    after = proposal['changes'][0]['after']
    original = compile_latex(source, {}, 'resume.tex')
    proposal.update(original_pdf_base64=base64.b64encode(original.pdf).decode(), original_preview=preview_pages(original.pdf), original_pages=original.pages)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1280, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base_url)
        page.locator('#resume').set_input_files({'name': 'resume.tex', 'mimeType': 'text/plain', 'buffer': source.encode()})
        page.locator('#job_text').fill(job)
        page.route('**/api/latex/propose', lambda route: route.fulfill(json=proposal))
        page.locator('#submit').click()
        expect(page.locator('#keyword-analysis')).to_be_visible()
        nosql = page.locator('#keyword-report tr').filter(has=page.get_by_role('cell', name='NoSQL', exact=True))
        postgres = page.locator('#keyword-report tr').filter(has=page.get_by_role('cell', name='PostgreSQL', exact=True))
        expect(nosql).to_contain_text('Selected for addition')
        expect(postgres).to_contain_text('Not currently listed')
        expect(page.locator('#changes .keyword-insertion')).to_contain_text('NoSQL')
        nosql_checkbox = page.get_by_role('checkbox', name='Add NoSQL', exact=True)
        cloud_checkbox = page.get_by_role('checkbox', name='Add public cloud', exact=True)
        expect(nosql_checkbox).to_be_visible()
        expect(cloud_checkbox).to_be_visible()
        # Two keywords in one skills line must be independently selectable.
        cloud_checkbox.uncheck()
        expect(nosql_checkbox).to_be_checked()
        expect(cloud_checkbox).not_to_be_checked()
        expect(page.locator('#changes .after')).to_contain_text('NoSQL')
        expect(page.locator('#changes .after')).not_to_contain_text('public cloud')
        page.locator('#compile').click()
        expect(page.locator('#compiled-result')).to_be_visible(timeout=20000)
        with page.expect_download() as partial_info:
            page.locator('#tex-download').click()
        partial = Path(partial_info.value.path()).read_text()
        assert 'NoSQL' in partial and 'public cloud' not in partial
        expect(nosql).to_contain_text('Added to compiled resume')
        with page.expect_download() as partial_info:
            page.locator('#latex-download').click()
        partial_text = '\n'.join(p.extract_text() or '' for p in PdfReader(partial_info.value.path()).pages)
        assert 'NoSQL' in partial_text and 'public cloud' not in partial_text
        # Keyword selection invalidates prior downloads and refreshes wording.
        cloud_checkbox.check()
        expect(page.locator('#compiled-result')).to_be_hidden()
        expect(page.locator('#changes .after')).to_contain_text('public cloud')
        page.locator('#clear-selection').click()
        expect(nosql).to_contain_text('Supported — not selected')
        page.locator('#compile').click()
        expect(page.locator('#compiled-result')).to_be_visible(timeout=20000)
        expect(nosql).to_contain_text('Supported, but not added')
        page.locator('#select-all').click()
        # Keep the earlier supported-only case by opting out of new skills.
        for checkbox in page.locator('#keyword-report input[data-manual="true"]').all():
            checkbox.uncheck()
        expect(nosql).to_contain_text('Selected for addition')
        page.locator('#compile').click()
        expect(page.locator('#compiled-result')).to_be_visible(timeout=20000)
        expect(nosql).to_contain_text('Added to compiled resume')
        expect(postgres).to_contain_text('Not added')
        with page.expect_download() as info:
            page.locator('#tex-download').click()
        edited = Path(info.value.path()).read_text()
        assert edited == source[:span.start] + after + source[span.end:]
        with page.expect_download() as info:
            page.locator('#latex-download').click()
        reader = PdfReader(info.value.path())
        text = '\n'.join(p.extract_text() or '' for p in reader.pages)
        assert 'NoSQL' in text and 'public cloud' in text and 'familiar' in text
        assert 'PostgreSQL' not in text and 'Cassandra' not in text and 'Azure' not in text
        assert len(reader.pages) == 1
        # New skills not found in the source remain independently selectable.
        postgres_checkbox = page.get_by_role('checkbox', name='Add PostgreSQL', exact=True)
        azure_checkbox = page.get_by_role('checkbox', name='Add Azure', exact=True)
        expect(postgres_checkbox).to_be_visible()
        expect(postgres_checkbox).not_to_be_checked()
        expect(azure_checkbox).not_to_be_checked()
        expect(page.locator('#keyword-report')).not_to_contain_text('Needs evidence')
        postgres_checkbox.check()
        expect(page.locator('#manual-keyword-preview')).to_contain_text('PostgreSQL')
        expect(page.locator('#compiled-result')).to_be_hidden()
        page.locator('#compile').click()
        expect(page.locator('#compiled-result')).to_be_visible(timeout=20000)
        expect(postgres).to_contain_text('Added to compiled resume')
        with page.expect_download() as info:
            page.locator('#tex-download').click()
        with_postgres = Path(info.value.path()).read_text()
        assert 'PostgreSQL' in with_postgres and 'Azure' not in with_postgres
        assert source.split(r'\section*{Technical Skills}')[0] == with_postgres.split(r'\section*{Technical Skills}')[0]
        with page.expect_download() as info:
            page.locator('#latex-download').click()
        downloaded = '\n'.join(p.extract_text() or '' for p in PdfReader(info.value.path()).pages)
        assert 'PostgreSQL' in downloaded and 'Azure' not in downloaded
        postgres_checkbox.uncheck()
        page.locator('#compile').click()
        expect(page.locator('#compiled-result')).to_be_visible(timeout=20000)
        with page.expect_download() as info:
            page.locator('#tex-download').click()
        assert 'PostgreSQL' not in Path(info.value.path()).read_text()
        page.screenshot(path='/tmp/resume-tailor-keywords-desktop.png', full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path='/tmp/resume-tailor-keywords-mobile.png', full_page=True)
        # A failed model response must not block keyword-only review or PDF export.
        with patch('app.rewrite._generate_json', side_effect=ModelResponseError('truncated', 'unfinished JSON')):
            fallback = propose_latex(source, job).model_dump()
        fallback.update(original_pdf_base64=base64.b64encode(original.pdf).decode(), original_preview=preview_pages(original.pdf), original_pages=original.pages)
        page.unroute('**/api/latex/propose')
        page.route('**/api/latex/propose', lambda route: route.fulfill(json=fallback))
        page.locator('#submit').click()
        expect(page.locator('#ai-warning')).to_be_visible()
        expect(page.locator('#ai-warning')).to_contain_text('stopped before completing')
        expect(page.locator('#status')).to_contain_text('You can still select keywords')
        page.get_by_role('checkbox', name='Add PostgreSQL', exact=True).check()
        page.locator('#compile').click()
        expect(page.locator('#compiled-result')).to_be_visible(timeout=20000)
        with page.expect_download() as info:
            page.locator('#latex-download').click()
        recovered = '\n'.join(p.extract_text() or '' for p in PdfReader(info.value.path()).pages)
        assert 'PostgreSQL' in recovered
        assert not errors, errors
        browser.close()
    print('Keyword browser check passed: evidence-backed NoSQL/public cloud insertion, per-keyword acceptance in a shared passage, gap reporting, selected-only coverage, unchanged LaTeX structure, real PDF/source downloads, and mobile layout.')


if __name__ == '__main__':
    run()
