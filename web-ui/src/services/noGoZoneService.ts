interface NoGoZonePoint {
  lat: number;
  lng: number;
}

interface NoGoZone {
  id: string;
  name: string;
  points: NoGoZonePoint[];
  area?: number;
  isValid: boolean;
  vertices: number;
  isEnabled: boolean;
  created_at?: string;
  updated_at?: string;
}

interface NoGoZoneCreateRequest {
  name: string;
  points: NoGoZonePoint[];
  isEnabled?: boolean;
}

interface NoGoZoneUpdateRequest {
  name?: string;
  points?: NoGoZonePoint[];
  isEnabled?: boolean;
}

class NoGoZoneService {
  private baseUrl = '/api/v1/maps';

  async getNoGoZones(): Promise<NoGoZone[]> {
    try {
      const response = await fetch(`${this.baseUrl}/no-go-zones`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const zones = await response.json();
      return Array.isArray(zones) ? zones : [];
    } catch (error) {
      console.error('Failed to fetch no-go zones:', error);
      throw new Error('Failed to load no-go zones');
    }
  }

  async createNoGoZone(zone: NoGoZoneCreateRequest): Promise<NoGoZone> {
    try {
      const validation = this.validateNoGoZone(zone.points);
      if (!validation.isValid) {
        throw new Error(validation.error);
      }

      const response = await fetch(`${this.baseUrl}/no-go-zones`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          name: zone.name,
          points: zone.points.map(p => ({
            latitude: p.lat,
            longitude: p.lng
          })),
          priority: 'HIGH' // All no-go zones are high priority
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `HTTP error! status: ${response.status}`);
      }

      return {
        id: `nogo-${Date.now()}`,
        name: zone.name,
        points: zone.points,
        area: validation.area,
        isValid: validation.isValid,
        vertices: zone.points.length,
        isEnabled: zone.isEnabled ?? true,
        created_at: new Date().toISOString()
      };
    } catch (error) {
      console.error('Failed to create no-go zone:', error);
      throw error instanceof Error ? error : new Error('Failed to create no-go zone');
    }
  }

  async updateNoGoZone(id: string, updates: NoGoZoneUpdateRequest): Promise<NoGoZone> {
    try {
      if (updates.points) {
        const validation = this.validateNoGoZone(updates.points);
        if (!validation.isValid) {
          throw new Error(validation.error);
        }
      }

      const response = await fetch(`${this.baseUrl}/no-go-zones/${id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          ...updates,
          points: updates.points?.map(p => ({
            latitude: p.lat,
            longitude: p.lng
          }))
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `HTTP error! status: ${response.status}`);
      }

      const result = await response.json();
      
      return {
        id,
        name: updates.name || '',
        points: updates.points || [],
        area: updates.points ? this.validateNoGoZone(updates.points).area : 0,
        isValid: updates.points ? this.validateNoGoZone(updates.points).isValid : true,
        vertices: updates.points?.length || 0,
        isEnabled: updates.isEnabled ?? true,
        updated_at: new Date().toISOString()
      };
    } catch (error) {
      console.error('Failed to update no-go zone:', error);
      throw error instanceof Error ? error : new Error('Failed to update no-go zone');
    }
  }

  async deleteNoGoZone(id: string): Promise<void> {
    try {
      const response = await fetch(`${this.baseUrl}/no-go-zones/${id}`, {
        method: 'DELETE',
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
    } catch (error) {
      console.error('Failed to delete no-go zone:', error);
      throw error instanceof Error ? error : new Error('Failed to delete no-go zone');
    }
  }

  async toggleNoGoZone(id: string, enabled: boolean): Promise<void> {
    try {
      await this.updateNoGoZone(id, { isEnabled: enabled });
    } catch (error) {
      console.error('Failed to toggle no-go zone:', error);
      throw error instanceof Error ? error : new Error('Failed to toggle no-go zone');
    }
  }

  // Clip no-go zone to yard boundaries
  async clipToYardBoundaries(zonePoints: NoGoZonePoint[], yardBoundaries: NoGoZonePoint[][]): Promise<NoGoZonePoint[]> {
    // This would typically use a geometry library like Turf.js for proper polygon clipping
    // For now, we'll implement a basic containment check
    if (yardBoundaries.length === 0) {
      return zonePoints;
    }

    // Use the first boundary as the primary yard boundary
    const primaryBoundary = yardBoundaries[0];
    
    // Simple point-in-polygon check - in a real implementation, you'd want proper clipping
    const clippedPoints = zonePoints.filter(point => 
      this.isPointInPolygon(point, primaryBoundary)
    );

    // If no points are inside, return original points (will be flagged as invalid)
    return clippedPoints.length >= 3 ? clippedPoints : zonePoints;
  }

  private validateNoGoZone(points: NoGoZonePoint[]): { isValid: boolean; error?: string; area?: number } {
    if (points.length < 3) {
      return { isValid: false, error: 'No-go zone must have at least 3 points' };
    }

    if (points.length > 100) {
      return { isValid: false, error: 'No-go zone cannot have more than 100 vertices' };
    }

    // Calculate area using shoelace formula
    const area = this.calculatePolygonArea(points);
    
    if (area < 1) {
      return { isValid: false, error: 'No-go zone area too small (minimum 1 m²)' };
    }

    // Check for self-intersection (basic check)
    if (this.hasSelfIntersection(points)) {
      return { isValid: false, error: 'No-go zone cannot have self-intersections' };
    }

    return { isValid: true, area };
  }

  private calculatePolygonArea(points: NoGoZonePoint[]): number {
    if (points.length < 3) return 0;

    let area = 0;
    const n = points.length;

    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      area += points[i].lat * points[j].lng;
      area -= points[j].lat * points[i].lng;
    }

    area = Math.abs(area) / 2;
    
    // Convert from degrees to square meters (approximate)
    const earthRadius = 6371000; // meters
    const avgLat = points.reduce((sum, p) => sum + p.lat, 0) / points.length;
    const metersPerDegreeLat = Math.PI * earthRadius / 180;
    const metersPerDegreeLng = metersPerDegreeLat * Math.cos(avgLat * Math.PI / 180);
    
    return area * metersPerDegreeLat * metersPerDegreeLng;
  }

  private hasSelfIntersection(points: NoGoZonePoint[]): boolean {
    const n = points.length;
    
    for (let i = 0; i < n; i++) {
      for (let j = i + 2; j < n; j++) {
        if (j === n - 1 && i === 0) continue; // Skip adjacent edges
        
        const p1 = points[i];
        const p2 = points[(i + 1) % n];
        const p3 = points[j];
        const p4 = points[(j + 1) % n];
        
        if (this.doLinesIntersect(p1, p2, p3, p4)) {
          return true;
        }
      }
    }
    
    return false;
  }

  private doLinesIntersect(p1: NoGoZonePoint, p2: NoGoZonePoint, p3: NoGoZonePoint, p4: NoGoZonePoint): boolean {
    const d1 = this.crossProduct(p3, p4, p1);
    const d2 = this.crossProduct(p3, p4, p2);
    const d3 = this.crossProduct(p1, p2, p3);
    const d4 = this.crossProduct(p1, p2, p4);
    
    if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) &&
        ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) {
      return true;
    }
    
    return false;
  }

  private crossProduct(a: NoGoZonePoint, b: NoGoZonePoint, c: NoGoZonePoint): number {
    return (b.lat - a.lat) * (c.lng - a.lng) - (b.lng - a.lng) * (c.lat - a.lat);
  }

  private isPointInPolygon(point: NoGoZonePoint, polygon: NoGoZonePoint[]): boolean {
    let inside = false;
    const n = polygon.length;
    
    for (let i = 0, j = n - 1; i < n; j = i++) {
      if (((polygon[i].lat > point.lat) !== (polygon[j].lat > point.lat)) &&
          (point.lng < (polygon[j].lng - polygon[i].lng) * (point.lat - polygon[i].lat) / (polygon[j].lat - polygon[i].lat) + polygon[i].lng)) {
        inside = !inside;
      }
    }
    
    return inside;
  }
}

export const noGoZoneService = new NoGoZoneService();
export type { NoGoZone, NoGoZonePoint, NoGoZoneCreateRequest, NoGoZoneUpdateRequest };
