# ETL or ELT?

This repo uses **ELT**: load the raw data first, then transform it with SQL inside BigQuery. This page says why, and walks through one real change: Finance stops counting `Returned` orders (session 3, exercise 4).

## ETL and ELT side by side

| Question | ETL | ELT (this repo) |
|---|---|---|
| Where does the transform run? | Outside the warehouse: a Python script or a server | Inside the warehouse, in SQL |
| What if a business rule changes? | Fix the code, then run it again from the source or from Raw | Fix the SQL, then rebuild from Bronze |
| Personal data (PII) | Remove or hide it before the load | It arrives as it is, so you must limit access |
| Who writes the transform? | Someone who writes Python | Anyone who writes SQL, including analysts |
| What limits the volume? | The machine that runs the script | The warehouse, and its bill |

Cloud warehouses made ELT cheap. Storage costs little, and compute grows with the query. Keeping the raw copy in Bronze costs almost nothing, and it lets you rebuild any layer later.

**ETL is still the better choice when:**
- You must not store some data at all (PII). Remove it before the load.
- The source is far bigger than the part you need. Filter first, and pay less to store and scan.
- The target is not a warehouse, and it needs data in an exact format.

## Try it: Finance stops counting Returned orders

Today the revenue rule is "every order except `Cancelled`". Finance now says: also leave out `Returned`, for the whole history.

### Three questions

| Question | Answer |
|---|---|
| Which way is cheaper, ETL or ELT? | **ELT.** Run again 2 Gold SQL files and 1 check. The source database is not touched, and Raw and Silver stay as they are. With ETL you rewrite the Python transform and run it again over the whole history, from Raw or from the source. That costs more hours and can load the source. I did not measure money or time. Use `--dry-run` below to see the bytes. |
| When would you still pick ETL? | When the data has PII you may not keep, or when the source is much bigger than what you use (see the list above). |
| Silver or Gold? | **Gold.** Silver says what the data is. Gold says what a number means. "Revenue" is a meaning, so the rule lives in Gold. If it lived in Silver, every rule change would rebuild Silver too. |

### Where the rule lives in this repo

| File | Why it has the rule |
|---|---|
| `dbt/models/marts/reporting/daily_revenue.sql` | Revenue and order count per day |
| `dbt/models/marts/reporting/monthly_revenue_by_category.sql` | Revenue and profit per category |
| `dbt/tests/gold_matches_silver.sql` | Compares the Gold total with Silver. It must use the same rule, or the test fails. |

`dbt/models/marts/reporting/return_rate_by_state.sql` counts returned orders on purpose. It does not change.

### Steps

1. In the three files above, change `status != 'Cancelled'` to `status NOT IN ('Cancelled', 'Returned')`.
2. Check that the rule is the same in all three files. `src/tests/transform/test_business_rules.py` fails if one file still has the old rule, or if a rule appears in Silver.

```powershell
uv run pytest src/tests/transform/test_business_rules.py
```

3. See how many bytes Gold will scan, before you pay for it.

```powershell
uv run python -m stylehub.transform.run_dbt gold --command compile
```

(`compile` only shows the SQL. To see the bytes, run the compiled SQL with a BigQuery dry run.)

4. Rebuild Gold only. dbt runs the tests too.

```powershell
uv run python -m stylehub.transform.run_dbt gold
```

Silver is not rebuilt and nothing is loaded again. That is the point of ELT with layers.

> [!NOTE]
> This is an exercise. The repo still counts every order except `Cancelled`. Step 4 needs BigQuery and has run on the current rule only. I did not try the changed rule.
