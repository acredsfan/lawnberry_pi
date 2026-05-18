const METERS_PER_LAT_DEG = 111320.0;
const northM = 5000000; // 5000 km
const eastM = 5000000; // 5000 km

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

console.log("Diff:  ", renderLat - clickLat, renderLon - clickLon);
