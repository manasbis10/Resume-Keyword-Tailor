"""Evidence-based matching of common engineering keywords, without model claims."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Keyword:
    term: str
    aliases: tuple[str, ...]
    evidence: tuple[tuple[str, ...], ...] = ()
    technical: bool = True


KEYWORDS = (
    Keyword("PostgreSQL", ("PostgreSQL", "Postgres")),
    Keyword("NoSQL", ("NoSQL",), (("non-relational",), ("DynamoDB",), ("MongoDB",), ("DocumentDB",), ("Cassandra",))),
    Keyword("RDBMS", ("RDBMS",), (("relational databases",), ("relational database",), ("PostgreSQL",), ("Postgres",), ("MySQL",), ("SQL Server",), ("Oracle Database",), ("Amazon RDS",), ("RDS",))),
    Keyword("RESTful micro-services", ("RESTful micro-services", "RESTful microservices"), (("REST APIs", "microservices"), ("REST API", "microservices"))),
    Keyword("REST APIs", ("REST APIs", "REST API", "RESTful APIs", "RESTful API")),
    Keyword("Microservices", ("microservices", "micro-services")),
    Keyword("AWS", ("AWS", "Amazon Web Services")),
    Keyword("Azure", ("Azure", "Microsoft Azure")),
    Keyword("GAE", ("GAE", "Google App Engine")),
    Keyword("Google Cloud", ("Google Cloud", "GCP")),
    Keyword("DynamoDB", ("DynamoDB",)),
    Keyword("Cassandra", ("Cassandra",)),
    Keyword("MongoDB", ("MongoDB",)),
    Keyword("DocumentDB", ("DocumentDB",)),
    Keyword("Oracle", ("Oracle", "Oracle Database", "Oracle DB")),
    Keyword("MySQL", ("MySQL",)),
    Keyword("SQL Server", ("SQL Server",)),
    Keyword("SQL", ("SQL",)),
    Keyword("Java", ("Java",)),
    Keyword("Kotlin", ("Kotlin",)),
    Keyword("Go", ("Go", "Golang")),
    Keyword("Scala", ("Scala",)),
    Keyword("Python", ("Python",)),
    Keyword("JavaScript", ("JavaScript",)),
    Keyword("TypeScript", ("TypeScript",)),
    Keyword("C++", ("C++",)),
    Keyword("C#", ("C#",)),
    Keyword("React", ("React", "React.js")),
    Keyword("GraphQL", ("GraphQL",)),
    Keyword("Docker", ("Docker",)),
    Keyword("Kubernetes", ("Kubernetes", "K8s")),
    Keyword("Kafka", ("Kafka",)),
    Keyword("Redis", ("Redis",)),
    Keyword("CloudWatch", ("CloudWatch",)),
    Keyword("SaaS", ("SaaS", "software as a service")),
    Keyword("PaaS", ("PaaS", "platform as a service")),
    Keyword("IaaS", ("IaaS", "infrastructure as a service")),
    Keyword("CI/CD", ("CI/CD", "continuous integration", "continuous delivery")),
    Keyword("Agile", ("Agile",)),
    Keyword("public cloud", ("public cloud",), (("AWS",), ("Azure",), ("Google Cloud",), ("GCP",)), False),
    Keyword("backend services", ("backend services", "backend applications"), technical=False),
    Keyword("distributed systems", ("distributed systems", "distributed environment", "distributed workflows"), technical=False),
    Keyword("scalability", ("scalability", "scalable"), technical=False),
    Keyword("performance", ("performance", "performant"), technical=False),
    Keyword("reliability", ("reliability", "reliable", "fault tolerance"), technical=False),
    Keyword("security", ("security", "secure"), technical=False),
    Keyword("monitoring", ("monitoring",), (("CloudWatch",),), False),
    Keyword("error reporting", ("error reporting",), technical=False),
    Keyword("code reviews", ("code reviews", "code review", "review code"), technical=False),
    Keyword("testing", ("testing", "tests", "test patterns"), technical=False),
    Keyword("documentation", ("documentation",), technical=False),
    Keyword("mentoring", ("mentoring", "mentor", "mentored"), technical=False),
    Keyword("sprint planning", ("sprint planning",), technical=False),
    Keyword("retrospectives", ("retrospectives", "retrospective"), technical=False),
    Keyword("cloud architecture", ("cloud architecture",), technical=False),
    Keyword("object-oriented programming", ("object-oriented programming", "object oriented programming", "OOP"), technical=False),
)


def contains(text: str, term: str) -> bool:
    pattern = re.escape(term).replace(r"\ ", r"\s+")
    # SaaS integrations with Oracle HCM are not evidence of Oracle database work.
    if term.casefold() == "oracle":
        pattern += r"(?!\s+HCM\b)"
    if term.casefold() == "relational database" or term.casefold() == "relational databases":
        pattern = r"(?<!non-)(?<!non )" + pattern
    return bool(re.search(r"(?<![\w])" + pattern + r"(?![\w+])", text, 0 if term == "Go" else re.I))


def visible_resume_text(source: str) -> str:
    """Use document text only: comments, preamble, commands and URLs aren't skills."""
    from app.latex_edit import TOKEN
    text = TOKEN.sub(lambda m: " " * len(m.group()) if m.group().startswith("%") else m.group(), source)
    start, end = text.find(r"\begin{document}"), text.rfind(r"\end{document}")
    if start < 0 or end < start:
        return ""
    text = text[start + len(r"\begin{document}"):end]
    text = re.sub(r"\\(?:href|url|input|include|includegraphics|label|ref|cite|begin|end|faIcon)(?:\[[^\]]*\])?\s*\{[^{}]*\}", " ", text)
    text = re.sub(r"\\[A-Za-z@]+\*?", " ", text)
    text = re.sub(r"\\([^A-Za-z])", r"\1", text)
    return re.sub(r"\s+", " ", text.replace("{", " ").replace("}", " ")).strip()


def present(keyword: Keyword, text: str) -> bool:
    return any(contains(text, alias) for alias in keyword.aliases)


def evidence_for(keyword: Keyword, text: str) -> list[str]:
    direct = next((alias for alias in keyword.aliases if contains(text, alias)), None)
    if direct:
        return [direct]
    return list(next((group for group in keyword.evidence if all(contains(text, term) for term in group)), ()))


def analyze_keywords(source: str, job_text: str) -> list[dict]:
    text = visible_resume_text(source)
    report = []
    for keyword in KEYWORDS:
        if not present(keyword, job_text):
            continue
        evidence = evidence_for(keyword, text)
        status = "present" if present(keyword, text) else "supported" if evidence else "missing"
        report.append({"keyword": keyword.term, "status": status, "evidence": ", ".join(evidence)})
    return report


def allowed_additions(context: str) -> set[str]:
    text = visible_resume_text(r"\begin{document}" + context + r"\end{document}")
    return {keyword.term for keyword in KEYWORDS if evidence_for(keyword, text)}


def validate_keyword_additions(before: str, after: str, context: str) -> set[str]:
    """Approve evidence-backed labels, not a technology borrowed from another job."""
    allowed = allowed_additions(context)
    for keyword in KEYWORDS:
        if keyword.technical and present(keyword, after) and not present(keyword, before) and keyword.term not in allowed:
            raise ValueError(f"The named technology keyword {keyword.term} is not supported by this passage's existing evidence.")
    return allowed


def skill_list(text: str) -> bool:
    hits = [keyword for keyword in KEYWORDS if keyword.technical and present(keyword, text)]
    return len(hits) >= 2 and ("," in text or " / " in text or " · " in text)


def coverage_report(report: list[dict], original: str, edited: str) -> list[dict]:
    before, after = visible_resume_text(original), visible_resume_text(edited)
    specs = {keyword.term: keyword for keyword in KEYWORDS}
    result = []
    for item in report:
        spec = specs[item["keyword"]]
        added = present(spec, after) and not present(spec, before)
        result.append({**item, "added": added, "in_output": present(spec, after)})
    return result



def report_for_terms(source: str, terms: list[str]) -> list[dict]:
    """Recompute a client-selected subset of known keywords; trust no client evidence."""
    text = visible_resume_text(source)
    requested = set(terms)
    result = []
    for keyword in KEYWORDS:
        if keyword.term not in requested:
            continue
        evidence = evidence_for(keyword, text)
        result.append({"keyword": keyword.term, "status": "present" if present(keyword, text) else "supported" if evidence else "missing", "evidence": ", ".join(evidence)})
    return result


def canonical_technical_text(text: str) -> str:
    """Normalize true aliases before checking preserved technology names."""
    for keyword in KEYWORDS:
        if not keyword.technical:
            continue
        for alias in sorted(keyword.aliases, key=len, reverse=True):
            pattern = re.escape(alias).replace(r"\ ", r"\s+")
            if alias.casefold() == "oracle":
                pattern += r"(?!\s+HCM\b)"
            text = re.sub(r"(?<![\w])" + pattern + r"(?![\w+])", lambda _: keyword.term, text, flags=0 if alias == "Go" else re.I)
    return text


def suggest_category_labels(source: str, report: list[dict], changes: list) -> list:
    """Offer simple, reviewable annotations even when the model misses a target.

    Label the actual supporting tool, never an entire mixed list: e.g.
    MongoDB (NoSQL), RDS (RDBMS), AWS (public cloud), CloudWatch (monitoring).
    """
    from app.latex_edit import apply_changes, editable_spans
    from app.models import LatexChange

    labels = {"NoSQL", "RDBMS", "public cloud", "monitoring"}
    current = {change.id: change for change in changes}
    spans = editable_spans(source)
    specs = {keyword.term: keyword for keyword in KEYWORDS}
    for item in report:
        term = item["keyword"]
        if term not in labels or item["status"] != "supported":
            continue
        edited = apply_changes(source, list(current.values()))
        if present(specs[term], visible_resume_text(edited)):
            continue
        for span in spans:
            if span.kind != "skills":
                continue
            existing = current.get(span.id)
            after = existing.after if existing else span.text
            evidence = evidence_for(specs[term], after)
            if not evidence:
                continue
            root = evidence[0]
            pattern = re.escape(root).replace(r"\ ", r"\s+")
            annotated = re.sub(r"(?<![\w])" + pattern + r"(?![\w+])", lambda match: f"{match.group()} ({term})", after, count=1, flags=re.I)
            reason = (existing.reason + " " if existing else "") + f"Add the JD term {term} using existing {root} evidence."
            change = LatexChange(id=span.id, before=span.text, after=annotated, reason=reason[:1000])
            try:
                apply_changes(source, [change])
            except ValueError:
                continue
            current[span.id] = change
            break
    return sorted(current.values(), key=lambda change: next(s.start for s in spans if s.id == change.id))



def with_keyword_choices(source: str, changes: list) -> list:
    """Prevalidate every subset of independently selectable category labels.

    Skills edits containing category labels use simple annotations. The original
    source is the empty selection, so rejecting one term never drops another.
    """
    from itertools import combinations
    from app.latex_edit import apply_changes, editable_spans
    from app.models import KeywordVariant

    spans = {span.id: span for span in editable_spans(source)}
    specs = {keyword.term: keyword for keyword in KEYWORDS}
    independent = {"NoSQL", "RDBMS", "public cloud", "monitoring"}
    result = []
    for change in changes:
        # The model cannot supply its own client-trusted variants.
        change.keyword_variants = []
        span = spans[change.id]
        terms = change.keywords_added
        if span.kind != "skills" or not terms or not set(terms) <= independent:
            result.append(change)
            continue
        variants = []
        valid = True
        for count in range(len(terms) + 1):
            for subset in combinations(terms, count):
                after = span.text
                for term in subset:
                    evidence = evidence_for(specs[term], after)
                    if not evidence:
                        valid = False
                        break
                    root = evidence[0]
                    pattern = re.escape(root).replace(r"\ ", r"\s+")
                    after = re.sub(r"(?<![\w])" + pattern + r"(?![\w+])", lambda match: f"{match.group()} ({term})", after, count=1, flags=re.I)
                try:
                    apply_changes(source, [change.model_copy(update={"after": after})])
                except ValueError:
                    valid = False
                if not valid:
                    break
                variants.append(KeywordVariant(keywords=list(subset), after=after))
            if not valid:
                break
        if valid:
            change.after = variants[-1].after
            change.keyword_variants = variants
            change.reason = "Add selected category keywords next to the existing tools that support them. Each keyword can be accepted separately in the coverage table."
        result.append(change)
    return result


def add_selected_skills(source: str, terms: list[str]) -> tuple[str, list[str]]:
    """Insert explicitly user-selected terms into existing skills text only.

    This is separate from AI patches: the user's checkbox choice supplies the
    new skill. AI suggestions still require their original passage evidence.
    """
    from app.latex_edit import editable_spans

    known = {keyword.term: keyword for keyword in KEYWORDS}
    if any(term not in known for term in terms):
        raise ValueError("Choose keywords from the job keyword table.")
    visible = visible_resume_text(source)
    additions = list(dict.fromkeys(term for term in terms if not present(known[term], visible)))
    if not additions:
        return source, []
    skills = [span for span in editable_spans(source) if span.kind == "skills"]
    if not skills:
        raise ValueError("Could not find an editable skills list. Add a plain-text skills list to the LaTeX source and try again.")
    databases = {"PostgreSQL", "NoSQL", "RDBMS", "DynamoDB", "Cassandra", "MongoDB", "DocumentDB", "Oracle", "MySQL", "SQL Server", "SQL", "Redis"}
    languages = {"Java", "Kotlin", "Go", "Scala", "Python", "JavaScript", "TypeScript", "C++", "C#"}
    cloud = {"AWS", "Azure", "GAE", "Google Cloud", "SaaS", "PaaS", "IaaS", "public cloud", "Docker", "Kubernetes"}
    grouped = {}
    for term in additions:
        family = databases if term in databases else languages if term in languages else cloud if term in cloud else set()
        labels = ("database", "data store") if term in databases else ("language",) if term in languages else ("cloud", "infrastructure") if term in cloud else ()
        def score(span):
            headings = re.findall(r"\\textbf\{([^{}]*)\}", source[max(0, span.start - 500):span.start])
            heading = headings[-1].casefold() if headings else ""
            return (any(label in heading for label in labels), sum(present(known[name], span.text) for name in family))
        target = max(skills, key=score) if family else skills[-1]
        grouped.setdefault(target.id, (target, []))[1].append(term)
    result = source
    escapes = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    for span, words in sorted(grouped.values(), key=lambda item: item[0].start, reverse=True):
        suffix = ", " + ", ".join("".join(escapes.get(char, char) for char in word) for word in words)
        position = span.end - 1 if span.text.endswith((".", ";")) else span.end
        result = result[:position] + suffix + result[position:]
    return result, additions
