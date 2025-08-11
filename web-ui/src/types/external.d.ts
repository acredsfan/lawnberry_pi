declare module '@turf/turf' {
  export interface Feature<G = any, P = any> {
    type: 'Feature';
    geometry: G;
    properties: P;
  }
  export interface PolygonGeometry {
    type: 'Polygon';
    coordinates: number[][][];
  }
  export type Polygon = PolygonGeometry;
  export function polygon(coordinates: number[][][], properties?: any): Feature<PolygonGeometry>;
  export function union(a: any, b: any): Feature<PolygonGeometry>;
}
