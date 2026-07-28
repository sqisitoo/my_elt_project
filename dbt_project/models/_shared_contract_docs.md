{% docs round_coordinate_contract__latitude %}

North-south coordinate in decimal degrees, normalized with the `round_coordinate()` macro before the model materializes it.

This documentation is the column-level surface of the same warehouse contract implemented in the `round_coordinate` macro: the normalized value is used for joins between OpenWeather observations and configured locations, and for surrogate-key generation where applicable.

TRAP: do not replace this with raw source precision or hand-written `round(..., 4)` logic in one model. If the coordinate-precision contract changes, update the `round_coordinate` macro and this doc block together, then roll the change out as a coordinated contract migration.

{% enddocs %}

{% docs round_coordinate_contract__longitude %}

East-west coordinate in decimal degrees, normalized with the `round_coordinate()` macro before the model materializes it.

This documentation is the column-level surface of the same warehouse contract implemented in the `round_coordinate` macro: the normalized value is used for joins between OpenWeather observations and configured locations, and for surrogate-key generation where applicable.

TRAP: do not replace this with raw source precision or hand-written `round(..., 4)` logic in one model. If the coordinate-precision contract changes, update the `round_coordinate` macro and this doc block together, then roll the change out as a coordinated contract migration.

{% enddocs %}