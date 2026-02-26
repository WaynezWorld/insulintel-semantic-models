-- =============================================================================
-- INSIGHT OF THE DAY FUNCTIONS
-- =============================================================================
-- Purpose: Compute correlations between lifestyle metrics and glucose outcomes
-- Author: Cortex Code
-- Created: 2026-02-26
-- =============================================================================

-- -----------------------------------------------------------------------------
-- FN_INSIGHT_OF_THE_DAY: Returns single best insight with actionable text
-- -----------------------------------------------------------------------------
-- Usage: SELECT * FROM TABLE(FN_INSIGHT_OF_THE_DAY('participant-uuid', 7))
-- Parameters:
--   P_PARTICIPANT_ID: User's participant ID
--   P_WINDOW_DAYS: Number of days to analyze (default 7, fallback to 30)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION DB_INSULINTEL.SCH_SEMANTIC.FN_INSIGHT_OF_THE_DAY(
    P_PARTICIPANT_ID VARCHAR,
    P_WINDOW_DAYS INT
)
RETURNS TABLE (
    participant_id VARCHAR,
    metric_key VARCHAR,
    metric_name VARCHAR,
    metric_category VARCHAR,
    glucose_metric VARCHAR,
    corr_r FLOAT,
    n_pairs INT,
    effect_size VARCHAR,
    effect_direction VARCHAR,
    robust_flag VARCHAR,
    insight_text VARCHAR,
    chart_recommended BOOLEAN
)
LANGUAGE SQL
AS
$$
    WITH 
    date_range AS (
        SELECT 
            DATEADD('day', -P_WINDOW_DAYS, CURRENT_DATE()) as start_date,
            DATEADD('day', -1, CURRENT_DATE()) as end_date
    ),
    
    -- GLUCOSE OUTCOMES (target variables)
    glucose_daily AS (
        SELECT PARTICIPANT_ID, READING_DATE, 
            TIR_IN_RANGE_PCT, 
            GLUCOSE_MEAN, 
            GLUCOSE_CV_PCT,
            TIME_ABOVE_RANGE_PCT,
            TIME_BELOW_RANGE_PCT,
            STABILITY_SCORE_0_100
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_GLUCOSE_DAILY_SUMMARY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID 
          AND DATASET_SOURCE = 'INSULINTEL'
          AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND DATA_COVERAGE_PCT >= 70
    ),
    
    -- Unpivot glucose metrics
    glucose_unpivot AS (
        SELECT PARTICIPANT_ID, READING_DATE, 'Time in Range (TIR)' as glucose_metric, TIR_IN_RANGE_PCT as glucose_value, 1 as gm_priority FROM glucose_daily WHERE TIR_IN_RANGE_PCT IS NOT NULL
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 'Average Glucose', GLUCOSE_MEAN, 2 FROM glucose_daily WHERE GLUCOSE_MEAN IS NOT NULL
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 'Glucose Variability (CV)', GLUCOSE_CV_PCT, 3 FROM glucose_daily WHERE GLUCOSE_CV_PCT IS NOT NULL
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 'Time Above Range', TIME_ABOVE_RANGE_PCT, 4 FROM glucose_daily WHERE TIME_ABOVE_RANGE_PCT IS NOT NULL
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 'Time Below Range', TIME_BELOW_RANGE_PCT, 5 FROM glucose_daily WHERE TIME_BELOW_RANGE_PCT IS NOT NULL
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 'Glucose Stability', STABILITY_SCORE_0_100, 6 FROM glucose_daily WHERE STABILITY_SCORE_0_100 IS NOT NULL
    ),
    
    -- CANDIDATE METRICS (predictor variables)
    candidate_metrics AS (
        -- ========== SLEEP METRICS ==========
        SELECT PARTICIPANT_ID, SLEEP_DATE as metric_date, 
            'SLEEP_DURATION' as metric_key, 'Sleep Duration' as metric_name, 'Sleep' as metric_category,
            SLEEP_DURATION_HOURS as metric_value, 1 as priority
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_SLEEP_DAILY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND SLEEP_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND SLEEP_DURATION_HOURS IS NOT NULL
        
        UNION ALL
        SELECT PARTICIPANT_ID, SLEEP_DATE, 
            'SLEEP_FRAGMENTATION', 'Sleep Fragmentation', 'Sleep',
            FRAGMENTATION_INDEX, 2
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_SLEEP_DAILY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND SLEEP_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND FRAGMENTATION_INDEX IS NOT NULL
        
        UNION ALL
        SELECT PARTICIPANT_ID, SLEEP_DATE, 
            'FASTING_GATE_SCORE', 'Fasting Readiness', 'Sleep',
            FASTING_GATE_SCORE, 3
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_SLEEP_DAILY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND SLEEP_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND FASTING_GATE_SCORE IS NOT NULL
        
        UNION ALL
        SELECT PARTICIPANT_ID, SLEEP_DATE, 
            'SLEEP_CONFIDENCE', 'Sleep Confidence', 'Sleep',
            SLEEP_CONFIDENCE, 4
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_SLEEP_DAILY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND SLEEP_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND SLEEP_CONFIDENCE IS NOT NULL
        
        -- ========== MEAL METRICS ==========
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 
            'TOTAL_CARBS', 'Daily Carbs', 'Nutrition',
            TOTAL_CARBS_G, 5
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_MEAL_DAILY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND TOTAL_CARBS_G IS NOT NULL
        
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 
            'MEAL_COUNT', 'Meals Per Day', 'Nutrition',
            MEAL_COUNT, 6
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_MEAL_DAILY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND MEAL_COUNT IS NOT NULL
        
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 
            'AVG_CARBS_PER_MEAL', 'Avg Carbs Per Meal', 'Nutrition',
            AVG_CARBS_G, 7
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_MEAL_DAILY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND AVG_CARBS_G IS NOT NULL
        
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 
            'TOTAL_PROTEIN', 'Daily Protein', 'Nutrition',
            TOTAL_PROTEIN_G, 8
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_MEAL_DAILY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND TOTAL_PROTEIN_G IS NOT NULL
        
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 
            'TOTAL_FAT', 'Daily Fat', 'Nutrition',
            TOTAL_FAT_G, 9
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_MEAL_DAILY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND TOTAL_FAT_G IS NOT NULL
        
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 
            'HIGH_CARB_MEALS', 'High Carb Meals', 'Nutrition',
            HIGH_CARB_MEALS_COUNT, 10
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_MEAL_DAILY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND HIGH_CARB_MEALS_COUNT IS NOT NULL
        
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 
            'AVG_PEAK_DELTA', 'Avg Glucose Spike After Meals', 'Nutrition',
            AVG_PEAK_DELTA, 11
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_MEAL_DAILY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND AVG_PEAK_DELTA IS NOT NULL
        
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 
            'AVG_TIME_TO_PEAK', 'Avg Time to Glucose Peak', 'Nutrition',
            AVG_TIME_TO_PEAK_MINUTES, 12
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_MEAL_DAILY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND AVG_TIME_TO_PEAK_MINUTES IS NOT NULL
        
        -- ========== BLOOD PRESSURE METRICS ==========
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 
            'SYSTOLIC_BP', 'Systolic Blood Pressure', 'Blood Pressure',
            SYSTOLIC_MEAN, 13
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_BP_DAILY_SUMMARY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND SYSTOLIC_MEAN IS NOT NULL
        
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 
            'DIASTOLIC_BP', 'Diastolic Blood Pressure', 'Blood Pressure',
            DIASTOLIC_MEAN, 14
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_BP_DAILY_SUMMARY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND DIASTOLIC_MEAN IS NOT NULL
        
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 
            'PULSE_PRESSURE', 'Pulse Pressure', 'Blood Pressure',
            PULSE_PRESSURE_MEAN, 15
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_BP_DAILY_SUMMARY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND PULSE_PRESSURE_MEAN IS NOT NULL
        
        UNION ALL
        SELECT PARTICIPANT_ID, READING_DATE, 
            'MAP', 'Mean Arterial Pressure', 'Blood Pressure',
            MAP_MEAN, 16
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_BP_DAILY_SUMMARY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND MAP_MEAN IS NOT NULL
        
        -- ========== EXERCISE METRICS (aggregated daily) ==========
        UNION ALL
        SELECT PARTICIPANT_ID, SESSION_DATE, 
            'EXERCISE_DURATION', 'Daily Exercise Duration', 'Exercise',
            SUM(DURATION_MINUTES), 17
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_EXERCISE_SESSIONS
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND SESSION_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND DURATION_MINUTES IS NOT NULL
        GROUP BY PARTICIPANT_ID, SESSION_DATE
        
        UNION ALL
        SELECT PARTICIPANT_ID, SESSION_DATE, 
            'EXERCISE_SESSIONS', 'Exercise Sessions Per Day', 'Exercise',
            COUNT(*), 18
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_EXERCISE_SESSIONS
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND SESSION_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
        GROUP BY PARTICIPANT_ID, SESSION_DATE
        
        UNION ALL
        SELECT PARTICIPANT_ID, SESSION_DATE, 
            'EXERCISE_CALORIES', 'Daily Active Calories', 'Exercise',
            SUM(ACTIVE_ENERGY_KCAL), 19
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_EXERCISE_SESSIONS
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND SESSION_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND ACTIVE_ENERGY_KCAL IS NOT NULL AND ACTIVE_ENERGY_KCAL < 10000
        GROUP BY PARTICIPANT_ID, SESSION_DATE
        
        UNION ALL
        SELECT PARTICIPANT_ID, SESSION_DATE, 
            'AVG_METS', 'Avg Exercise Intensity (METs)', 'Exercise',
            AVG(AVG_METS), 20
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_EXERCISE_SESSIONS
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' 
          AND SESSION_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range)
          AND AVG_METS IS NOT NULL
        GROUP BY PARTICIPANT_ID, SESSION_DATE
    ),
    
    -- Pair metrics with glucose outcomes
    paired AS (
        SELECT cm.*, gu.glucose_metric, gu.glucose_value, gu.gm_priority
        FROM candidate_metrics cm 
        JOIN glucose_unpivot gu ON cm.PARTICIPANT_ID = gu.PARTICIPANT_ID AND cm.metric_date = gu.READING_DATE
    ),
    
    -- Compute correlations
    corrs AS (
        SELECT 
            PARTICIPANT_ID, metric_key, metric_name, metric_category, glucose_metric,
            MIN(priority) as priority, MIN(gm_priority) as gm_priority,
            COUNT(*)::INT as n_pairs, 
            CORR(metric_value, glucose_value)::FLOAT as corr_r,
            AVG(metric_value) as metric_mean,
            AVG(glucose_value) as glucose_mean
        FROM paired 
        GROUP BY 1,2,3,4,5 
        HAVING COUNT(*) >= 4 AND CORR(metric_value, glucose_value) IS NOT NULL
    ),
    
    -- Add labels and flags
    labeled AS (
        SELECT *,
            CASE 
                WHEN ABS(corr_r) >= 0.5 THEN 'strong' 
                WHEN ABS(corr_r) >= 0.3 THEN 'moderate' 
                WHEN ABS(corr_r) >= 0.15 THEN 'weak'
                ELSE 'negligible' 
            END as effect_size,
            CASE WHEN corr_r > 0 THEN 'positive' ELSE 'negative' END as effect_direction,
            CASE 
                WHEN n_pairs >= 6 AND ABS(corr_r) >= 0.35 THEN 'ROBUST' 
                WHEN n_pairs >= 5 AND ABS(corr_r) >= 0.25 THEN 'MODERATE'
                ELSE 'WEAK' 
            END as robust_flag
        FROM corrs 
        WHERE ABS(corr_r) >= 0.1
    ),
    
    -- Rank by effect size and correlation strength (prefer TIR as glucose metric)
    ranked AS (
        SELECT *, 
            ROW_NUMBER() OVER (
                ORDER BY 
                    CASE effect_size WHEN 'strong' THEN 1 WHEN 'moderate' THEN 2 WHEN 'weak' THEN 3 ELSE 4 END,
                    gm_priority,
                    ABS(corr_r) DESC, 
                    priority
            ) as rn 
        FROM labeled
    ),
    
    -- Build result
    result AS (
        SELECT 
            PARTICIPANT_ID::VARCHAR as participant_id,
            metric_key::VARCHAR, 
            metric_name::VARCHAR, 
            metric_category::VARCHAR,
            glucose_metric::VARCHAR,
            ROUND(corr_r, 3)::FLOAT as corr_r, 
            n_pairs::INT,
            effect_size::VARCHAR, 
            effect_direction::VARCHAR, 
            robust_flag::VARCHAR,
            (
                'Your ' || metric_name || ' shows a ' || effect_size || ' ' || effect_direction || 
                ' correlation (r=' || ROUND(corr_r, 2)::VARCHAR || ') with ' || glucose_metric || 
                ' over the past ' || P_WINDOW_DAYS::VARCHAR || ' days.' ||
                CASE 
                    WHEN effect_direction = 'negative' AND glucose_metric = 'Time in Range (TIR)' 
                        THEN ' Lower ' || metric_name || ' may help improve your TIR.'
                    WHEN effect_direction = 'positive' AND glucose_metric = 'Time in Range (TIR)' 
                        THEN ' Higher ' || metric_name || ' appears to support better TIR.'
                    WHEN effect_direction = 'positive' AND glucose_metric LIKE '%Variability%' 
                        THEN ' Reducing ' || metric_name || ' may help stabilize glucose.'
                    ELSE ''
                END
            )::VARCHAR as insight_text,
            (n_pairs >= 6)::BOOLEAN as chart_recommended
        FROM ranked WHERE rn = 1
    )
    
    SELECT * FROM result
    
    UNION ALL
    
    -- Fallback when no insights found
    SELECT 
        P_PARTICIPANT_ID, 
        'INSUFFICIENT_DATA', 
        'Insufficient Data', 
        NULL,
        NULL, NULL, NULL, NULL, NULL, 
        'WEAK',
        'Not enough data for a reliable insight. Keep logging your meals, sleep, and exercise!', 
        FALSE
    WHERE NOT EXISTS (SELECT 1 FROM result)
    
    LIMIT 1
$$;


-- -----------------------------------------------------------------------------
-- FN_ALL_METRIC_CORRELATIONS: Returns all significant correlations ranked
-- -----------------------------------------------------------------------------
-- Usage: SELECT * FROM TABLE(FN_ALL_METRIC_CORRELATIONS('participant-uuid', 30))
-- Returns all metrics with |r| >= 0.1 and n_pairs >= 4
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION DB_INSULINTEL.SCH_SEMANTIC.FN_ALL_METRIC_CORRELATIONS(
    P_PARTICIPANT_ID VARCHAR,
    P_WINDOW_DAYS INT
)
RETURNS TABLE (
    participant_id VARCHAR,
    metric_key VARCHAR,
    metric_name VARCHAR,
    metric_category VARCHAR,
    glucose_metric VARCHAR,
    corr_r FLOAT,
    n_pairs INT,
    effect_size VARCHAR,
    effect_direction VARCHAR,
    robust_flag VARCHAR,
    rank_num INT
)
LANGUAGE SQL
AS
$$
    WITH 
    date_range AS (
        SELECT DATEADD('day', -P_WINDOW_DAYS, CURRENT_DATE()) as start_date, DATEADD('day', -1, CURRENT_DATE()) as end_date
    ),
    glucose_daily AS (
        SELECT PARTICIPANT_ID, READING_DATE, TIR_IN_RANGE_PCT, GLUCOSE_MEAN, GLUCOSE_CV_PCT, TIME_ABOVE_RANGE_PCT, TIME_BELOW_RANGE_PCT, STABILITY_SCORE_0_100
        FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_GLUCOSE_DAILY_SUMMARY
        WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL'
          AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range) AND DATA_COVERAGE_PCT >= 70
    ),
    glucose_unpivot AS (
        SELECT PARTICIPANT_ID, READING_DATE, 'TIR' as glucose_metric, TIR_IN_RANGE_PCT as glucose_value, 1 as gm_priority FROM glucose_daily WHERE TIR_IN_RANGE_PCT IS NOT NULL
        UNION ALL SELECT PARTICIPANT_ID, READING_DATE, 'Avg Glucose', GLUCOSE_MEAN, 2 FROM glucose_daily WHERE GLUCOSE_MEAN IS NOT NULL
        UNION ALL SELECT PARTICIPANT_ID, READING_DATE, 'Glucose CV', GLUCOSE_CV_PCT, 3 FROM glucose_daily WHERE GLUCOSE_CV_PCT IS NOT NULL
    ),
    candidate_metrics AS (
        -- Sleep
        SELECT PARTICIPANT_ID, SLEEP_DATE as metric_date, 'SLEEP_DURATION' as metric_key, 'Sleep Duration' as metric_name, 'Sleep' as metric_category, SLEEP_DURATION_HOURS as metric_value, 1 as priority FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_SLEEP_DAILY WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' AND SLEEP_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range) AND SLEEP_DURATION_HOURS IS NOT NULL
        UNION ALL SELECT PARTICIPANT_ID, SLEEP_DATE, 'FRAGMENTATION', 'Sleep Fragmentation', 'Sleep', FRAGMENTATION_INDEX, 2 FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_SLEEP_DAILY WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' AND SLEEP_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range) AND FRAGMENTATION_INDEX IS NOT NULL
        -- Nutrition
        UNION ALL SELECT PARTICIPANT_ID, READING_DATE, 'TOTAL_CARBS', 'Daily Carbs', 'Nutrition', TOTAL_CARBS_G, 3 FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_MEAL_DAILY WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range) AND TOTAL_CARBS_G IS NOT NULL
        UNION ALL SELECT PARTICIPANT_ID, READING_DATE, 'MEAL_COUNT', 'Meal Count', 'Nutrition', MEAL_COUNT, 4 FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_MEAL_DAILY WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range) AND MEAL_COUNT IS NOT NULL
        UNION ALL SELECT PARTICIPANT_ID, READING_DATE, 'TOTAL_PROTEIN', 'Daily Protein', 'Nutrition', TOTAL_PROTEIN_G, 5 FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_MEAL_DAILY WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range) AND TOTAL_PROTEIN_G IS NOT NULL
        UNION ALL SELECT PARTICIPANT_ID, READING_DATE, 'TOTAL_FAT', 'Daily Fat', 'Nutrition', TOTAL_FAT_G, 6 FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_MEAL_DAILY WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range) AND TOTAL_FAT_G IS NOT NULL
        UNION ALL SELECT PARTICIPANT_ID, READING_DATE, 'HIGH_CARB_MEALS', 'High Carb Meals', 'Nutrition', HIGH_CARB_MEALS_COUNT, 7 FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_MEAL_DAILY WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range) AND HIGH_CARB_MEALS_COUNT IS NOT NULL
        UNION ALL SELECT PARTICIPANT_ID, READING_DATE, 'AVG_PEAK_DELTA', 'Avg Glucose Spike', 'Nutrition', AVG_PEAK_DELTA, 8 FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_MEAL_DAILY WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range) AND AVG_PEAK_DELTA IS NOT NULL
        -- Blood Pressure
        UNION ALL SELECT PARTICIPANT_ID, READING_DATE, 'SYSTOLIC_BP', 'Systolic BP', 'Blood Pressure', SYSTOLIC_MEAN, 9 FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_BP_DAILY_SUMMARY WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range) AND SYSTOLIC_MEAN IS NOT NULL
        UNION ALL SELECT PARTICIPANT_ID, READING_DATE, 'DIASTOLIC_BP', 'Diastolic BP', 'Blood Pressure', DIASTOLIC_MEAN, 10 FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_BP_DAILY_SUMMARY WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' AND READING_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range) AND DIASTOLIC_MEAN IS NOT NULL
        -- Exercise (daily aggregated)
        UNION ALL SELECT PARTICIPANT_ID, SESSION_DATE, 'EXERCISE_DURATION', 'Daily Exercise', 'Exercise', SUM(DURATION_MINUTES), 11 FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_EXERCISE_SESSIONS WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' AND SESSION_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range) AND DURATION_MINUTES IS NOT NULL GROUP BY 1,2
        UNION ALL SELECT PARTICIPANT_ID, SESSION_DATE, 'EXERCISE_SESSIONS', 'Exercise Sessions', 'Exercise', COUNT(*), 12 FROM DB_INSULINTEL.SCH_SEMANTIC.V_GOLD_EXERCISE_SESSIONS WHERE PARTICIPANT_ID = P_PARTICIPANT_ID AND DATASET_SOURCE = 'INSULINTEL' AND SESSION_DATE BETWEEN (SELECT start_date FROM date_range) AND (SELECT end_date FROM date_range) GROUP BY 1,2
    ),
    paired AS (
        SELECT cm.*, gu.glucose_metric, gu.glucose_value, gu.gm_priority
        FROM candidate_metrics cm JOIN glucose_unpivot gu ON cm.PARTICIPANT_ID = gu.PARTICIPANT_ID AND cm.metric_date = gu.READING_DATE
    ),
    corrs AS (
        SELECT PARTICIPANT_ID, metric_key, metric_name, metric_category, glucose_metric, MIN(priority) as priority, MIN(gm_priority) as gm_priority,
            COUNT(*)::INT as n_pairs, CORR(metric_value, glucose_value)::FLOAT as corr_r
        FROM paired GROUP BY 1,2,3,4,5 HAVING COUNT(*) >= 4 AND CORR(metric_value, glucose_value) IS NOT NULL
    ),
    labeled AS (
        SELECT *,
            CASE WHEN ABS(corr_r) >= 0.5 THEN 'strong' WHEN ABS(corr_r) >= 0.3 THEN 'moderate' WHEN ABS(corr_r) >= 0.15 THEN 'weak' ELSE 'negligible' END as effect_size,
            CASE WHEN corr_r > 0 THEN 'positive' ELSE 'negative' END as effect_direction,
            CASE WHEN n_pairs >= 6 AND ABS(corr_r) >= 0.35 THEN 'ROBUST' WHEN n_pairs >= 5 AND ABS(corr_r) >= 0.25 THEN 'MODERATE' ELSE 'WEAK' END as robust_flag
        FROM corrs WHERE ABS(corr_r) >= 0.1
    )
    SELECT 
        PARTICIPANT_ID::VARCHAR as participant_id, metric_key::VARCHAR, metric_name::VARCHAR, metric_category::VARCHAR, glucose_metric::VARCHAR,
        ROUND(corr_r, 3)::FLOAT as corr_r, n_pairs::INT, effect_size::VARCHAR, effect_direction::VARCHAR, robust_flag::VARCHAR,
        ROW_NUMBER() OVER (ORDER BY CASE effect_size WHEN 'strong' THEN 1 WHEN 'moderate' THEN 2 WHEN 'weak' THEN 3 ELSE 4 END, gm_priority, ABS(corr_r) DESC)::INT as rank_num
    FROM labeled
    ORDER BY rank_num
$$;


-- =============================================================================
-- USAGE EXAMPLES
-- =============================================================================
-- Get single best insight (7 days):
-- SELECT * FROM TABLE(FN_INSIGHT_OF_THE_DAY('participant-uuid', 7));

-- Get single best insight (30 days fallback):
-- SELECT * FROM TABLE(FN_INSIGHT_OF_THE_DAY('participant-uuid', 30));

-- Get all correlations for deeper analysis:
-- SELECT * FROM TABLE(FN_ALL_METRIC_CORRELATIONS('participant-uuid', 30)) ORDER BY RANK_NUM;

-- Get top 5 insights:
-- SELECT * FROM TABLE(FN_ALL_METRIC_CORRELATIONS('participant-uuid', 30)) WHERE RANK_NUM <= 5;
