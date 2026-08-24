\pset pager off
BEGIN READ ONLY;

\echo ''
\echo '=== A0. KEY CENSUS — read this before trusting any percentage below ==='
SELECT s.task_type, k.key, count(*) AS sessions
  FROM sessions s, LATERAL jsonb_object_keys(s.payload) AS k(key)
 WHERE s.payload IS NOT NULL AND jsonb_typeof(s.payload) = 'object'
 GROUP BY 1,2 ORDER BY 1, sessions DESC;

\echo ''
\echo '=== A0b. keys carried by one quiz QUESTION object ==='
SELECT k.key, count(*) AS questions
  FROM sessions s,
       LATERAL jsonb_array_elements(s.payload->'questions') AS q,
       LATERAL jsonb_object_keys(q) AS k(key)
 WHERE s.task_type = 'quiz' AND jsonb_typeof(s.payload->'questions') = 'array'
 GROUP BY 1 ORDER BY questions DESC;

\echo ''
\echo '=== A0c. DENOMINATORS — if any of these is small, its percentage is void ==='
SELECT 'quiz_prompt' AS kind, count(*) AS n
  FROM sessions s, LATERAL jsonb_array_elements(s.payload->'questions') AS q
 WHERE s.task_type='quiz' AND jsonb_typeof(s.payload->'questions')='array'
   AND (q->>'prompt') IS NOT NULL
UNION ALL SELECT 'chunk_sentence', count(*) FROM chunks
   WHERE COALESCE(full_sentence,chunk) IS NOT NULL
UNION ALL SELECT 'reading_body', count(*) FROM readings WHERE body IS NOT NULL
UNION ALL SELECT 'quiz_sessions_with_scenario', count(*) FROM sessions
   WHERE task_type='quiz' AND NULLIF(trim(payload->>'scenario'),'') IS NOT NULL;

\echo ''
\echo '=== A1. work-vocabulary fraction by content source, with a 95% CI ==='
WITH content AS (
    SELECT 'quiz_prompt'::text AS kind, (q->>'prompt') AS body
      FROM sessions s, LATERAL jsonb_array_elements(s.payload->'questions') AS q
     WHERE s.task_type = 'quiz'
       AND jsonb_typeof(s.payload->'questions') = 'array'
       AND (q->>'prompt') IS NOT NULL
    UNION ALL
    SELECT 'chunk_sentence', COALESCE(c.full_sentence, c.chunk)
      FROM chunks c WHERE COALESCE(c.full_sentence, c.chunk) IS NOT NULL
    UNION ALL
    SELECT 'reading_body', r.body
      FROM readings r WHERE r.body IS NOT NULL
), hit AS (
    SELECT kind,
           (body ~* '\m(client|campaign|deploy|meeting|deadline|q3|stakeholder|budget|launch|report)\M') AS is_work
      FROM content
)
SELECT CASE WHEN GROUPING(kind) = 1 THEN '(ALL SOURCES)' ELSE kind END AS kind,
       count(*) AS n,
       count(*) FILTER (WHERE is_work) AS work_rows,
       round(100.0*count(*) FILTER (WHERE is_work)/NULLIF(count(*),0), 1) AS work_pct,
       round(196.0*sqrt(
           (count(*) FILTER (WHERE is_work)::numeric/NULLIF(count(*),0))
         * (1 - count(*) FILTER (WHERE is_work)::numeric/NULLIF(count(*),0))
         / NULLIF(count(*),0)), 1) AS ci95_pp
  FROM hit GROUP BY ROLLUP (kind) ORDER BY GROUPING(kind), kind;

\echo ''
\echo '=== A2. DIRECTION ONLY (n is ~29) — chunks split by declared track ==='
SELECT CASE WHEN GROUPING(c.track) = 1 THEN '(ALL TRACKS)'
            ELSE COALESCE(c.track,'(null track)') END AS track,
       count(*) AS n,
       count(*) FILTER (WHERE COALESCE(c.full_sentence,c.chunk) ~* '\m(client|campaign|deploy|meeting|deadline|q3|stakeholder|budget|launch|report)\M') AS work_rows,
       round(100.0 * count(*) FILTER (WHERE COALESCE(c.full_sentence,c.chunk) ~* '\m(client|campaign|deploy|meeting|deadline|q3|stakeholder|budget|launch|report)\M')
             / NULLIF(count(*),0), 1) AS work_pct
  FROM chunks c WHERE COALESCE(c.full_sentence,c.chunk) IS NOT NULL
 GROUP BY ROLLUP (c.track) ORDER BY GROUPING(c.track), 1;

\echo '=== A3. per-term hit counts — the ban list, derived rather than assumed ==='
WITH content AS (
    SELECT (q->>'prompt') AS body
      FROM sessions s, LATERAL jsonb_array_elements(s.payload->'questions') AS q
     WHERE s.task_type='quiz' AND jsonb_typeof(s.payload->'questions')='array' AND (q->>'prompt') IS NOT NULL
    UNION ALL SELECT COALESCE(c.full_sentence,c.chunk) FROM chunks c WHERE COALESCE(c.full_sentence,c.chunk) IS NOT NULL
    UNION ALL SELECT r.body FROM readings r WHERE r.body IS NOT NULL
)
SELECT term, count(*) FILTER (WHERE body ~* ('\m'||term||'\M')) AS hits
  FROM content, unnest(ARRAY['client','campaign','deploy','meeting','deadline','q3','stakeholder',
                             'budget','launch','report','sprint','standup','kpi','deliverable',
                             'onboarding','pipeline','revenue','quarter','sync','roadmap','eod']) AS term
 GROUP BY term ORDER BY hits DESC;

\echo '=== B. quiz-scenario frequency distribution ==='
SELECT COALESCE(NULLIF(trim(payload->>'scenario'),''),'(none)') AS scenario,
       count(*) AS quizzes,
       round(100.0*count(*)/sum(count(*)) OVER (), 1) AS pct
  FROM sessions WHERE task_type='quiz' AND payload IS NOT NULL
 GROUP BY 1 ORDER BY quizzes DESC;

\echo '=== B2. lopsidedness in one line ==='
SELECT count(*) AS distinct_scenarios,
       sum(n) AS total_quizzes,
       round(100.0*max(n)/NULLIF(sum(n),0),1) AS top_scenario_pct
  FROM (SELECT COALESCE(NULLIF(trim(payload->>'scenario'),''),'(none)') AS s, count(*) AS n
          FROM sessions WHERE task_type='quiz' AND payload IS NOT NULL GROUP BY 1) t;

COMMIT;
