import pandas as pd
from services import stocks_data
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.ensemble import RandomForestClassifier

FEATURES = ["daily_return", "five_day_return",
            "moving_average_ratio", "ten_day_rolling_std"]


def build_features(closes):
    df = pd.DataFrame({"close": closes})
    df["daily_return"] = df["close"].pct_change()
    df["five_day_return"] = df["close"].pct_change(5)
    df["moving_average"] = df["close"].rolling(20).mean()
    df["moving_average_ratio"] = (df["close"] / df["moving_average"]) - 1
    df["ten_day_rolling_std"] = df["daily_return"].rolling(10).std()
    df["tomorrow_return"] = df["daily_return"].shift(-1)
    df = df.dropna()
    df["target"] = (df["tomorrow_return"] > 0).astype(int)
    df = df.drop(columns=["moving_average", "tomorrow_return", "close"])
    return df


def train_and_evaluate(df, model):
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
    baseline = y_test.mean()

    print(f"\n--- {type(model).__name__} ---")
    print(f"Model accuracy: {accuracy:.1%}")
    print(f"Baseline: {baseline:.1%}")
    print("Predicted up rate:", y_prediction.mean())

    return model, scaler, accuracy, baseline


if __name__ == "__main__":
    from services.user_context import CANDIDATES
    wins = 0
    edges = []
    for ticker, _ in CANDIDATES:
        history = stocks_data.get_history(ticker, period="5y")
        if history is None:
            print(f"{ticker}: Skipped -- No Data")
            continue
        df = build_features(history["closes"])
        model, scaler, accuracy, baseline = train_and_evaluate(df, RandomForestClassifier(
            n_estimators=200, max_depth=5, random_state=42))
        edge = accuracy - baseline
        edges.append(edge)
        if edge > 0:
            wins += 1
        print(
            f"{ticker}: model {accuracy:.1%}, baseline {baseline:.1%}, edge {edge:+.1%}")
    print(f"Wins: {wins}/{len(edges)}")
    print(f"Average edge: {(sum(edges) / len(edges))}")
