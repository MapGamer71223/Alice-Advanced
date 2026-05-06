import re
from textblob import TextBlob

# optional transformer model caching
_transformer_classifier = None


def detect_emotion(text):
    """
    Enhanced emotion detection:
    - Emoji weighting
    - Multi-trigger scoring
    - Sarcasm detection
    - Negation awareness
    - Optional transformer fallback

    Returns: (emotion_label, confidence)
    """

    if not text or not text.strip():
        return ("neutral", 0.5)

    text_lower = text.lower()
    scores = {}

    # -------------------------------------------------------------------
    # 1. EMOJI-BASED WEIGHTING (supports multiple emojis)
    # -------------------------------------------------------------------
    emoji_map = {
        "happy": ["😂", "😊", "😃", "😁", "😍", "🥰", "😄", "😉", "😆"],
        "sad": ["😢", "😭", "😔", "😞", "☹️"],
        "angry": ["😡", "😠", "🤬"],
        "surprised": ["😱", "😲", "🤯", "😳"],
        "grateful": ["🙏", "🙌"],
        "bored": ["😐", "😒", "😶"],
        "sarcastic": ["😏", "🙄"],
        "fearful": ["😨", "😰", "😥"]
    }

    for emotion, emojis in emoji_map.items():
        for emo in emojis:
            if emo in text:
                scores[emotion] = scores.get(emotion, 0) + 0.9

    # -------------------------------------------------------------------
    # 2. KEYWORD-BASED WEIGHTING (multi-matches increase confidence)
    # -------------------------------------------------------------------
    keyword_map = {
        "grateful": ["thanks", "thank you", "appreciate", "means a lot"],
        "angry": ["hate", "angry", "furious", "annoyed", "rage", "irritated"],
        "frustrated": ["why won't", "nothing works", "i swear", "so annoying"],
        "sad": ["sad", "down", "depressed", "lost", "cry", "lonely"],
        "happy": ["happy", "yay", "awesome", "great", "nice", "glad"],
        "excited": ["omg", "let's go", "hyped", "can't wait"],
        "fearful": ["afraid", "scared", "worried", "fear", "anxiety"],
        "surprised": ["wow", "unbelievable", "what the hell", "no way"],
        "bored": ["bored", "meh", "whatever", "dull"],
        "sarcastic": ["yeah right", "sure sure", "obviously", "as if"],
        "confused": ["what", "huh", "idk", "i don't get it", "confused"],
    }

    for emotion, keywords in keyword_map.items():
        for k in keywords:
            if k in text_lower:
                scores[emotion] = scores.get(emotion, 0) + 0.7

    # -------------------------------------------------------------------
    # 3. NEGATION + POLARITY (TextBlob)
    # -------------------------------------------------------------------
    blob = TextBlob(text)
    polarity = blob.polarity
    is_negated = bool(re.search(r"\b(not|never|n't|no way|none)\b", text_lower))

    if polarity > 0.4 and not is_negated:
        scores["happy"] = scores.get("happy", 0) + polarity
    elif polarity > 0.4 and is_negated:
        scores["sarcastic"] = scores.get("sarcastic", 0) + 0.8

    if polarity < -0.35:
        if is_negated:
            scores["sarcastic"] = scores.get("sarcastic", 0) + 0.4
        else:
            scores["sad"] = scores.get("sad", 0) + abs(polarity)

    if -0.2 < polarity < 0.2 and not scores:
        scores["neutral"] = 0.5

    # -------------------------------------------------------------------
    # 4. Transformer fallback (only if no strong emotion detected)
    # -------------------------------------------------------------------
    try:
        global _transformer_classifier
        if not _transformer_classifier:
            from transformers import pipeline
            _transformer_classifier = pipeline(
                "text-classification",
                model="j-hartmann/emotion-english-distilroberta-base",
                top_k=1
            )
        if not scores or max(scores.values()) < 0.7:
            out = _transformer_classifier(text)[0]
            label = out["label"].lower()
            score = out["score"]
            return (label, float(score))
    except Exception:
        pass

    # -------------------------------------------------------------------
    # 5. Final emotion = max-scoring emotion
    # -------------------------------------------------------------------
    if not scores:
        return ("neutral", 0.6)

    best_emotion = max(scores, key=scores.get)
    confidence = min(1.0, scores[best_emotion])

    return (best_emotion, confidence)
