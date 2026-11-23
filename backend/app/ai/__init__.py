"""
AI Module, the four capabilities required by Section V-iv of the
Software Architecture, plus the chatbot from Section V-v:

    forecasting   , electricity demand forecasting (SARIMA)
    anomaly       , anomaly detection (IsolationForest)
    segmentation  , customer segmentation (KMeans)
    recommender   , personalised recommendations (rules over real signals)
    chatbot       , customer support assistant (LLM + grounded fallback)

Each module degrades gracefully if its ML dependency is missing, so the API
never fails because a model could not be fitted.
"""
