"""Relevance scoring using VLM analysis."""

import json
import re
from dataclasses import dataclass

from kibotos.evaluator.vlm import VLMClient, get_vlm_client


@dataclass
class RelevanceScores:
    """Detailed relevance scores."""

    action_match: float  # Does video show the requested action?
    perspective_correct: float  # Is it first-person/robot perspective?
    demonstration_quality: float  # Is the demonstration clear and complete?
    training_utility: float  # Would this be useful for training a robot?


@dataclass
class RelevanceResult:
    """Result of relevance evaluation."""

    score: float
    scores: RelevanceScores
    reasoning: str
    raw_response: str


EVALUATION_PROMPT = """You are evaluating a video submission for a robot training dataset.

REQUESTED TASK:
Category: {category}
Task: {task}
Scenario: {scenario}

The images shown are keyframes extracted from a video submission. Evaluate how well this video matches the requested task.

EVALUATION CRITERIA (score each 0.0 to 1.0):

1. action_match: Does the video show the requested action being performed?
   - 1.0: The exact requested action is clearly shown
   - 0.7: A similar action is shown
   - 0.3: Only partially related action
   - 0.0: Completely different action or no action

2. perspective_correct: Is this filmed from a first-person or robot-mounted perspective?
   - 1.0: Clear first-person/egocentric view (head, chest, or wrist mounted)
   - 0.7: Robot's viewpoint or close approximation
   - 0.3: Third-person but close to the action
   - 0.0: Third-person far view or unrelated angle

3. demonstration_quality: Is the action demonstration clear and complete?
   - 1.0: Full action shown start to finish, clear and unobstructed
   - 0.7: Mostly complete, minor issues
   - 0.3: Partial demonstration or significant quality issues
   - 0.0: Unable to see the action clearly

4. training_utility: Would this video be useful for training a robot?
   - 1.0: Excellent training data - clear, relevant, good perspective
   - 0.7: Good training data with minor limitations
   - 0.3: Limited utility due to quality or relevance issues
   - 0.0: Not useful for robot training

Respond ONLY with valid JSON in this exact format:
{{
    "action_match": <float 0-1>,
    "perspective_correct": <float 0-1>,
    "demonstration_quality": <float 0-1>,
    "training_utility": <float 0-1>,
    "reasoning": "<brief 1-2 sentence explanation>"
}}"""


class RelevanceEvaluator:
    """Evaluates video relevance to prompts using VLM."""

    # Score weights for final computation
    WEIGHTS = {
        "action_match": 0.4,
        "perspective_correct": 0.2,
        "demonstration_quality": 0.2,
        "training_utility": 0.2,
    }

    def __init__(self, vlm_client: VLMClient | None = None):
        self.vlm = vlm_client or get_vlm_client()

    async def evaluate(
        self,
        video_path: str,
        category: str,
        task: str,
        scenario: str,
        n_frames: int = 5,
    ) -> RelevanceResult:
        """
        Evaluate how well a video matches a prompt.

        Args:
            video_path: Path to the video file
            category: Prompt category (e.g., "manipulation")
            task: Prompt task (e.g., "grasp")
            scenario: Prompt scenario description
            n_frames: Number of keyframes to analyze

        Returns:
            RelevanceResult with scores and reasoning
        """
        prompt = EVALUATION_PROMPT.format(
            category=category,
            task=task,
            scenario=scenario,
        )

        response = await self.vlm.analyze_video(
            video_path=video_path,
            prompt=prompt,
            n_frames=n_frames,
            max_tokens=512,
        )

        # Parse JSON response
        scores, reasoning = self._parse_response(response.content)

        # Compute weighted final score
        final_score = (
            self.WEIGHTS["action_match"] * scores.action_match
            + self.WEIGHTS["perspective_correct"] * scores.perspective_correct
            + self.WEIGHTS["demonstration_quality"] * scores.demonstration_quality
            + self.WEIGHTS["training_utility"] * scores.training_utility
        )

        return RelevanceResult(
            score=round(final_score, 4),
            scores=scores,
            reasoning=reasoning,
            raw_response=response.content,
        )

    def _parse_response(self, content: str) -> tuple[RelevanceScores, str]:
        """Parse VLM response into scores."""
        # Try to extract JSON from response
        try:
            # First try direct parse
            data = json.loads(content)
        except json.JSONDecodeError:
            # Try to find JSON in the response
            json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}

        # Extract scores with defaults
        def get_score(key: str, default: float = 0.0) -> float:
            val = data.get(key, default)
            try:
                score = float(val)
                return max(0.0, min(1.0, score))  # Clamp to [0, 1]
            except (ValueError, TypeError):
                return default

        scores = RelevanceScores(
            action_match=get_score("action_match"),
            perspective_correct=get_score("perspective_correct"),
            demonstration_quality=get_score("demonstration_quality"),
            training_utility=get_score("training_utility"),
        )

        reasoning = data.get("reasoning", "No reasoning provided")

        return scores, reasoning


# Singleton instance
_evaluator: RelevanceEvaluator | None = None


def get_relevance_evaluator() -> RelevanceEvaluator:
    """Get or create the relevance evaluator instance."""
    global _evaluator
    if _evaluator is None:
        _evaluator = RelevanceEvaluator()
    return _evaluator
