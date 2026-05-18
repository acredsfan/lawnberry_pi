const METERS_PER_LAT_DEG = 111320.0;

function removeDisplayOffset(lat, lon, northM, eastM) {
  if (northM === 0 && eastM === 0) return [lat, lon];
  const metersPerLonDeg = METERS_PER_LAT_DEG * Math.cos(lat * Math.PI / 180);
  return [lat - northM / METERS_PER_LAT_DEG, lon - eastM / metersPerLonDeg];
}

function applyDisplayOffset(lat, lon, northM, eastM) {
  if (northM === 0 && eastM === 0) return [lat, lon];
  const metersPerLonDeg = METERS_PER_LAT_DEG * Math.cos(lat * Math.PI / 180);
  return [lat + northM / METERS_PER_LAT_DEG, lon + eastM / metersPerLonDeg];
}

const visualLat = 40.0001;
const visualLon = -80.0001;
const northM = 10;
const eastM = 10;

const [trueLat, trueLon] = removeDisplayOffset(visualLat, visualLon, northM, eastM);
const [finalLat, finalLon] = applyDisplayOffset(trueLat, trueLon, northM, eastM);

console.log("Visual:", visualLat, visualLon);
console.log("True:", trueLat, trueLon);
console.log("Final:", finalLat, finalLon);
console.log("Diff Lat:", finalLat - visualLat);
console.log("Diff Lon:", finalLon - visualLon);
