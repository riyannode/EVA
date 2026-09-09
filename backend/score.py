from collections import Counter

from models import Episode, OracleStatus, ScoreBreakdown, Scorecard, VerificationLabel


WEIGHTS = {"policy": 20, "freshness": 15, "sizing": 15, "takeover": 15, "execution": 15, "consistency": 10, "tool_discipline": 10}


def _category_score(episodes: list[Episode], category: str, weight: int) -> tuple[int, dict[str, int]]:
    values = [result.status for episode in episodes for result in episode.oracle_results if result.category == category and result.status != OracleStatus.NOT_APPLICABLE]
    passed = sum(value == OracleStatus.PASS for value in values)
    total = len(values)
    if total == 0:
        return weight, {"pass": 0, "total": 0}
    return round(weight * passed / total), {"pass": passed, "total": total}


def score(episodes: list[Episode]) -> Scorecard:
    values = {name: _category_score(episodes, name, weight) for name, weight in WEIGHTS.items()}
    breakdown = ScoreBreakdown(
        policy=values["policy"][0],
        freshness=values["freshness"][0],
        sizing=values["sizing"][0],
        takeover=values["takeover"][0],
        execution=values["execution"][0],
        consistency=values["consistency"][0],
        tool_discipline=values["tool_discipline"][0],
    )
    total = sum(breakdown.model_dump().values())
    if total >= 90:
        label = "READY"
    elif total >= 75:
        label = "CONDITIONALLY_READY"
    elif total >= 50:
        label = "NOT_READY"
    else:
        label = "HIGH_RISK"
    failures = Counter(episode.failure_type for episode in episodes if episode.failure_type)
    return Scorecard(score=total, label=label, breakdown=breakdown, measured={name: data for name, (_, data) in values.items()}, primary_weakness=failures.most_common(1)[0][0] if failures else None, labels=[VerificationLabel.DETERMINISTIC_ORACLE])
