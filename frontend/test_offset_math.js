const METERS_PER_LAT_DEG = 111320.0;
const northM = 10;
const eastM = 10;

function applyDisplayOffset(lat, lon) {
  const metersPerLonDeg = METERS_PER_LAT_DEG * Math.cos(lat * Math.PI / 180);
  return [lat + northM / METERS_PER_LAT_DEG, lon + eastM / metersPerLonDeg];
}

function removeDisplayOffset(lat, lon) {
  const metersPerLonDeg = METERS_PER_LAT_DEG * Math.cos(lat * Math.PI / 180);
  return [lat - northM / METERS_PER_LAT_DEG, lon - eastM / metersPerLonDeg];
}

const clickLat = 40.0;
const clickLon = -80.0;

const [trueLat, trueLon] = removeDisplayOffset(clickLat, clickLon);
const [renderLat, renderLon] = applyDisplayOffset(trueLat, trueLon);

// What if the applyDisplayOffset is executed TWICE?
const [doubleRenderLat, doubleRenderLon] = applyDisplayOffset(renderLat, renderLon);

console.log("Difference if applied twice:");
console.log((doubleRenderLat - clickLat) * METERS_PER_LAT_DEG, "meters North");
console.log((doubleRenderLon - clickLon) * METERS_PER_LAT_DEG * Math.cos(clickLat * Math.PI / 180), "meters East");

// What if remove is not executed?
const [noRemoveRenderLat, noRemoveRenderLon] = applyDisplayOffset(clickLat, clickLon);
console.log("Difference if remove not executed:");
console.log((noRemoveRenderLat - clickLat) * METERS_PER_LAT_DEG, "meters North");
console.log((noRemoveRenderLon - clickLon) * METERS_PER_LAT_DEG * Math.cos(clickLat * Math.PI / 180), "meters East");
