"""Phase 1: Scoring calculations, weighted skill aggregation, and adaptive difficulty progression logic."""
from typing import List, Dict, Any, Optional

def compute_weighted_score(answers_data: List[Dict[str, Any]], skill_weights_list: List[Dict[str, Any]]) -> float:
    """Computes the overall interview score by weighting average scores per skill tag.
    
    Edge cases handled:
    - If a skill has zero answered questions, it is excluded and the remaining skill weights are re-normalized.
    - If no answers exist, returns 0.0 without division by zero errors.
    """
    if not answers_data:
        return 0.0

    # 1. Group answered scores by skill_tag
    scores_by_skill: Dict[str, List[float]] = {}
    for item in answers_data:
        skill = item.get("skill_tag", "General")
        score = float(item.get("score", 0.0))
        if skill not in scores_by_skill:
            scores_by_skill[skill] = []
        scores_by_skill[skill].append(score)

    # 2. Extract weights map
    weights_map: Dict[str, float] = {}
    if isinstance(skill_weights_list, list):
        for sw in skill_weights_list:
            weights_map[sw.get("skill", "")] = float(sw.get("weight", 0.0))
    elif isinstance(skill_weights_list, dict):
        weights_map = {k: float(v) for k, v in skill_weights_list.items()}

    # 3. Calculate average score for evaluated skills and sum applicable weights
    applicable_skills: Dict[str, float] = {}
    total_applicable_weight = 0.0

    for skill, scores in scores_by_skill.items():
        if scores:
            avg_score = sum(scores) / len(scores)
            skill_weight = weights_map.get(skill, 1.0 / max(1, len(scores_by_skill)))
            applicable_skills[skill] = avg_score
            total_applicable_weight += skill_weight

    if not applicable_skills or total_applicable_weight <= 0:
        # Fallback to unweighted simple average if weights are zero/missing
        all_scores = [s for sub in scores_by_skill.values() for s in sub]
        return round(sum(all_scores) / len(all_scores), 1) if all_scores else 0.0

    # 4. Compute re-normalized weighted sum
    weighted_sum = 0.0
    for skill, avg_score in applicable_skills.items():
        skill_weight = weights_map.get(skill, 1.0 / len(applicable_skills))
        normalized_weight = skill_weight / total_applicable_weight
        weighted_sum += avg_score * normalized_weight

    return round(min(10.0, max(0.0, weighted_sum)), 1)


def determine_difficulty_progression(last_score: float, current_difficulty: str = "medium") -> str:
    """Calculates the target difficulty level for the next question based on the candidate's last score.
    
    Rules:
    - score >= 7.0 -> increase difficulty
    - score <= 3.0 -> decrease difficulty
    - 3.0 < score < 7.0 -> maintain current difficulty
    """
    levels = ["easy", "medium", "hard"]
    curr_diff = current_difficulty.lower() if current_difficulty else "medium"
    curr_idx = levels.index(curr_diff) if curr_diff in levels else 1

    if last_score >= 7.0:
        next_idx = min(2, curr_idx + 1)
    elif last_score <= 3.0:
        next_idx = max(0, curr_idx - 1)
    else:
        next_idx = curr_idx

    return levels[next_idx]
