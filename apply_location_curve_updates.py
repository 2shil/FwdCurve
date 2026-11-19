from pathlib import Path
import shutil

APP_PATH = Path(__file__).with_name("API_Gas_ICIS_fwd_curve_IV_2.py")
MARKER = "# Analyst context for matched location spreads"
CURVE_MARKER = "# Contract-level forward price curve"

source = APP_PATH.read_text(encoding="utf-8")
updated = source

# Replace the current hub-level spread summary with contract analytics plus summary insights.
summary_start = "    summary_rows = []\n    for hub_label, group in spreads.groupby(\"comparison_hub\"):\n"
summary_end = "    return spreads, pd.DataFrame(summary_rows), skipped\n"
if MARKER not in updated:
    start = updated.find(summary_start)
    if start < 0:
        raise SystemExit("Could not find location-spread summary block; app was not changed.")
    end = updated.find(summary_end, start)
    if end < 0:
        raise SystemExit("Could not find end of location-spread function; app was not changed.")
    end += len(summary_end)
    replacement = '''    # Analyst context for matched location spreads
    spreads["spread_pct_of_reference"] = np.where(
        spreads["reference_price"].ne(0),
        spreads["spread"] / spreads["reference_price"] * 100.0,
        np.nan,
    )
    spreads["spread_position"] = np.select(
        [spreads["spread"] > 0, spreads["spread"] < 0],
        ["Premium", "Discount"],
        default="At parity",
    )
    spreads["days_to_delivery"] = (
        pd.to_datetime(spreads["period_start"]).dt.normalize()
        - pd.Timestamp.today().normalize()
    ).dt.days

    spreads = spreads.sort_values(
        ["comparison_hub", "period_start", "period_end"]
    ).reset_index(drop=True)
    by_hub = spreads.groupby("comparison_hub", sort=False)["spread"]
    spreads["spread_change_vs_previous_period"] = by_hub.diff()
    spreads["spread_rank_within_hub"] = by_hub.rank(
        method="dense", ascending=False
    )

    def _spread_zscore(values):
        std = values.std(ddof=0)
        if len(values) < 2 or pd.isna(std) or std == 0:
            return pd.Series(np.nan, index=values.index)
        return (values - values.mean()) / std

    spreads["spread_zscore_within_hub"] = (
        spreads.groupby("comparison_hub")["spread"].transform(_spread_zscore)
    )
    spreads["is_spread_outlier"] = spreads["spread_zscore_within_hub"].abs() >= 2.0

    summary_rows = []
    for hub_label, group in spreads.groupby("comparison_hub"):
        group = group.sort_values(["period_start", "period_end"])
        nearest = group.iloc[0]
        widest_premium = group.loc[group["spread"].idxmax()]
        widest_discount = group.loc[group["spread"].idxmin()]
        nearest_value = float(nearest["spread"])
        front_to_back = float(group.iloc[-1]["spread"] - nearest_value)

        if nearest_value > 0:
            position = "premium"
        elif nearest_value < 0:
            position = "discount"
        else:
            position = "at parity"

        if front_to_back > 0:
            curve_context = "The spread widens towards the back of the matched curve."
        elif front_to_back < 0:
            curve_context = "The spread narrows towards the back of the matched curve."
        else:
            curve_context = "The spread is broadly unchanged across matched contracts."

        summary_rows.append({
            "comparison_hub": hub_label,
            "reference_hub": nearest["reference_hub"],
            "matched_delivery_periods": len(group),
            "nearest_period": nearest["period_label"],
            "nearest_period_spread": nearest_value,
            "nearest_period_spread_pct": nearest["spread_pct_of_reference"],
            "nearest_position": position,
            "mean_spread": float(group["spread"].mean()),
            "median_spread": float(group["spread"].median()),
            "widest_premium_period": widest_premium["period_label"],
            "widest_premium": float(widest_premium["spread"]),
            "widest_discount_period": widest_discount["period_label"],
            "widest_discount": float(widest_discount["spread"]),
            "front_to_back_change": front_to_back,
            "analyst_insight": (
                f"{hub_label} is at a {position} to {nearest['reference_hub']} "
                f"for the nearest matched contract ({nearest_value:.2f}). {curve_context}"
            ),
        })

    return spreads, pd.DataFrame(summary_rows), skipped
'''
    updated = updated[:start] + replacement + updated[end:]

# Make the heading match the summary content (earliest contract, not latest).
updated = updated.replace(
    'st.subheader("Latest location spread insights")',
    'st.subheader("Location spread summary and analyst insights")',
)

# Display analyst metrics in the contract table and include them in chart hover details.
updated = updated.replace(
    'hover_data=["period_label","period_end","comparison_price","reference_price"],',
    'hover_data=["period_label","period_end","comparison_price","reference_price",\n'
    '                    "spread_pct_of_reference","spread_change_vs_previous_period",\n'
    '                    "spread_position","is_spread_outlier"],',
)

# Insert the per-contract forward curve once, after period aggregation is built.
curve_anchor = '        period_prices_assess = compute_period_prices_from_assessments(df_assess, method=assess_method)\n'
if CURVE_MARKER not in updated:
    if curve_anchor not in updated:
        raise SystemExit("Could not find assessment period-price calculation; app was not changed.")
    curve_code = '''

        # Contract-level forward price curve
        if not period_prices_assess.empty:
            forward_curve = period_prices_assess.copy()
            forward_curve["delivery_start"] = forward_curve["period_startDate"].apply(parse_date_flexible)
            forward_curve["delivery_end"] = forward_curve["period_endDate"].apply(parse_date_flexible)
            forward_curve["period_price"] = pd.to_numeric(forward_curve["period_price"], errors="coerce")
            forward_curve = (
                forward_curve.dropna(subset=["delivery_start", "period_price"])
                .sort_values(["delivery_start", "delivery_end"])
                .reset_index(drop=True)
            )

            if not forward_curve.empty:
                st.subheader("Forward price curve by delivery contract")
                st.caption(
                    "One point per delivery contract for the selected PriceAssessment specification "
                    "using the chosen assessment aggregation method."
                )
                fig_forward = px.line(
                    forward_curve,
                    x="delivery_start",
                    y="period_price",
                    markers=True,
                    hover_data={
                        "period_label": True,
                        "delivery_start": True,
                        "delivery_end": True,
                        "n_assessments": True,
                        "period_price": ":.4f",
                    },
                    title="Forward price curve by contract",
                    labels={
                        "delivery_start": "Delivery period start",
                        "period_price": "Assessment price",
                    },
                )
                fig_forward.update_traces(line=dict(width=2), marker=dict(size=8))
                fig_forward.update_layout(
                    xaxis_title="Delivery period start",
                    yaxis_title="Assessment price",
                    hovermode="x unified",
                    height=500,
                )
                st.plotly_chart(fig_forward, use_container_width=True)
                st.subheader("Forward curve contracts")
                st.dataframe(forward_curve, use_container_width=True)
                st_download_df(
                    "Download forward curve contracts CSV",
                    forward_curve,
                    file_name="forward_curve_contracts.csv",
                    mime="text/csv",
                )
'''
    updated = updated.replace(curve_anchor, curve_anchor + curve_code, 1)

if updated == source:
    raise SystemExit("No changes were applied; check the app file and patch markers.")

backup = APP_PATH.with_suffix(APP_PATH.suffix + ".bak")
if not backup.exists():
    shutil.copy2(APP_PATH, backup)
APP_PATH.write_text(updated, encoding="utf-8")
print(f"Updated {APP_PATH.name}; original backup: {backup.name}")
print("Please run: python -m py_compile API_Gas_ICIS_fwd_curve_IV_2.py")
