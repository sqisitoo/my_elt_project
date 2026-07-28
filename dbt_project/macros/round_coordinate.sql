{#
    Coordinate-rounding contract.

    Use this macro everywhere dbt models normalize latitude/longitude for joins
    or surrogate keys. Four decimal places are part of the warehouse contract
    between configured locations and OpenWeather observations.

    Keep the shared doc blocks `round_coordinate_contract__latitude` and
    `round_coordinate_contract__longitude` in sync with this contract. They are
    the user-facing column documentation for models materialized from this rule.

    TRAP: if one model drifts away from this shared precision, dbt will usually
    still build successfully. The failure mode is semantic: joins to
    `dim_location` can start returning NULL `location_id`, and downstream fact
    tests catch it only after the contract has already been broken.

    If the rule ever changes, treat it as a coordinated contract migration and
    backfill, not as a local formatting tweak in one model.
#}
{% macro round_coordinate(column_name) %}
        round({{ column_name }}, 4)
{% endmacro %}