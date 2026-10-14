-- Question: how many events, users and sessions per day and event type?
-- Reads only the columns it needs from the partitioned Silver table.

SELECT
  event_date,
  event_type,
  COUNT(*) AS n_events,
  COUNT(DISTINCT user_id) AS n_users,
  COUNT(DISTINCT user_session) AS n_sessions
FROM {{ ref('fact_events') }}
GROUP BY event_date, event_type
