import pandas as pd
from services import stocks_data
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.ensemble import RandomForestClassifier
from services.user_context import CANDIDATES

# Goal: predict tomorrow's direction for a company stock, either the stock price goes higher (positive)
#       or it goes down (negative)

# Solution -- Build a machine learning model that (roughly) predicts if the stock is going to go up
#             or down tomorrow.
FEATURES = ["daily_return", "five_day_return",
            "moving_average_ratio", "ten_day_rolling_std", "sixty_day_rolling_std"]
MINIMUM_EDGE = 0.05


def build_features(closes):
    df = pd.DataFrame({"close": closes})
    df["daily_return"] = df["close"].pct_change()
    df["five_day_return"] = df["close"].pct_change(5)
    df["moving_average"] = df["close"].rolling(20).mean()
    df["moving_average_ratio"] = (df["close"] / df["moving_average"]) - 1
    df["ten_day_rolling_std"] = df["daily_return"].rolling(10).std()
    df["sixty_day_rolling_std"] = df["daily_return"].rolling(60).std()
    df = df.drop(columns=["moving_average", "close"])
    return df


def add_direction_target(df):
    df = df.copy()
    df["tomorrow_return"] = df["daily_return"].shift(-1)
    df = df.dropna()
    df["target"] = (df["tomorrow_return"] > 0).astype(int)
    df = df.drop(columns=["tomorrow_return"])
    return df


def add_volatility_target(df):
    df = df.copy()
    df["future_volatility"] = df["daily_return"].rolling(5).std().shift(-5)
    df = df.dropna()
    df["target"] = (df["future_volatility"] >
                    df["sixty_day_rolling_std"]).astype(int)
    df = df.drop(columns="future_volatility")
    return df


def train_and_evaluate(df, model, verbose=True):
    X = df[FEATURES]
    y = df["target"]
    split = int(len(df) * 0.8)
    X_train = X.iloc[:split]
    X_test = X.iloc[split:]
    y_train = y.iloc[:split]
    y_test = y.iloc[split:]

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model.fit(X_train_scaled, y_train)
    y_prediction = model.predict(X_test_scaled)
    accuracy = accuracy_score(y_test, y_prediction)
    baseline = max(y_test.mean(), 1 - y_test.mean())

    if verbose:
        print(f"\n--- {type(model).__name__} ---")
        print(f"Model accuracy: {accuracy:.1%}")
        print(f"Baseline: {baseline:.1%}")
        print("Predicted 1-rate:", y_prediction.mean())

    return model, scaler, accuracy, baseline


def run_models(name, target, model):
    wins = 0
    edges = []
    print(f"\n=== {name} ===")
    for ticker, _ in CANDIDATES:
        history = stocks_data.get_history(ticker, period="5y")
        if history is None:
            print(f"{ticker}: Skipped -- No Data")
            continue
        df = build_features(history["closes"])
        df = target(df)
        model, scaler, accuracy, baseline = train_and_evaluate(
            df, model, verbose=False)
        edge = accuracy - baseline
        edges.append(edge)
        if edge > 0:
            wins += 1
        print(
            f"{ticker}: model {accuracy:.1%}, baseline {baseline:.1%}, edge {edge:+.1%}")
    print(f"Wins: {wins}/{len(edges)}")
    print(f"Average edge: {(sum(edges) / len(edges)):.1%}")


def predict_next_week(ticker):
    history = stocks_data.get_history(ticker, period="5y")
    if history is None:
        return None
    features = build_features(history["closes"])

    latest_row = features[FEATURES].iloc[[-1]]
    if latest_row.isna().values.any():
        return None
    labeled = add_volatility_target(features)

    if len(labeled) < 200:
        return None
    _, _, accuracy, baseline = train_and_evaluate(
        labeled, LogisticRegression(), verbose=False)
    X = labeled[FEATURES]
    y = labeled["target"]
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    model = LogisticRegression()
    model.fit(X_scaled, y)
    scaled_latest_row = scaler.transform(latest_row)
    predicted_probability = model.predict_proba(scaled_latest_row)[0][1]
    return {
        "probability": float(predicted_probability),
        "label": "Higher than usual" if predicted_probability > 0.5 else "Lower than usual",
        "accuracy": float(accuracy),
        "baseline": float(baseline),
        "edge": float(accuracy - baseline),
        "reliability": (accuracy - baseline) >= MINIMUM_EDGE
    }


if __name__ == "__main__":
    # run_models("Volatility: Logistic Regression",
    #            add_volatility_target, LogisticRegression())

    print(predict_next_week("SPY"))
    print(predict_next_week("AAPL"))
