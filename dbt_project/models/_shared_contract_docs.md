{% docs round_coordinate_contract__latitude %}

North-south coordinate in decimal degrees, normalized to the shared precision defined by the `round_coordinate()` contract.

This documentation is the column-level surface of the same warehouse contract implemented in the `round_coordinate` macro: the normalized value is used for joins between OpenWeather observations and configured locations, and for surrogate-key generation where applicable.

TRAP: if one model stops using the shared coordinate precision and keeps raw source precision or a hand-written local variant instead, dbt will usually still build successfully. The failure mode is semantic, not syntactic: joins from weather or air-quality facts to `dim_location` can start returning NULL `location_id`, and the breakage is then caught only by downstream `not_null` and `relationships` tests in `fct_weather` and `fct_air_quality`.

If the coordinate-precision contract changes, update the `round_coordinate` macro and this doc block together, then roll the change out as a coordinated contract migration.

{% enddocs %}

{% docs round_coordinate_contract__longitude %}

East-west coordinate in decimal degrees, normalized to the shared precision defined by the `round_coordinate()` contract.

This documentation is the column-level surface of the same warehouse contract implemented in the `round_coordinate` macro: the normalized value is used for joins between OpenWeather observations and configured locations, and for surrogate-key generation where applicable.

TRAP: if one model stops using the shared coordinate precision and keeps raw source precision or a hand-written local variant instead, dbt will usually still build successfully. The failure mode is semantic, not syntactic: joins from weather or air-quality facts to `dim_location` can start returning NULL `location_id`, and the breakage is then caught only by downstream `not_null` and `relationships` tests in `fct_weather` and `fct_air_quality`.

If the coordinate-precision contract changes, update the `round_coordinate` macro and this doc block together, then roll the change out as a coordinated contract migration.

{% enddocs %}