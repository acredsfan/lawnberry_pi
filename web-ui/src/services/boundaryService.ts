interface BoundaryPoint {
  lat: number;
  lng: number;
}

interface Boundary {
  id: string;
  name: string;
  points: BoundaryPoint[];
  area?: number;
  isValid: boolean;
  vertices: number;
  created_at?: string;
  updated_at?: string;
}

interface BoundaryCreateRequest {
  name: string;
  points: BoundaryPoint[];
}

interface BoundaryUpdateRequest {
  name?: string;
  points?: BoundaryPoint[];
}

class BoundaryService {
  private baseUrl = '/api/v1/maps';

  async getBoundaries(): Promise<Boundary[]> {
    try {
      const response = await fetch(`${this.baseUrl}/boundaries`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const boundaries = await response.json();
      return Array.isArray(boundaries) ? boundaries : [];
    } catch (error) {
      console.error('Failed to fetch boundaries:', error);
      throw new Error('Failed to load boundaries');
    }
  }

  async createBoundary(boundary: BoundaryCreateRequest): Promise<Boundary> {
    try {
      const validation = this.validateBoundary(boundary.points);
      if (!validation.isValid) {
        throw new Error(validation.error);
      }

      const response = await fetch(`${this.baseUrl}/boundaries`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          name: boundary.name,
          points: boundary.points.map(p => ({
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
        id: `boundary-${Date.now()}`,
        name: boundary.name,
        points: boundary.points,
        area: validation.area,
        isValid: validation.isValid,
        vertices: boundary.points.length,
        created_at: new Date().toISOString()
      };
    } catch (error) {
      console.error('Failed to create boundary:', error);
      throw error instanceof Error ? error : new Error('Failed to create boundary');
    }
  }

  async deleteBoundary(id: string): Promise<void> {
    try {
      const response = await fetch(`${this.baseUrl}/boundaries/${id}`, {
        method: 'DELETE',
        credentials: 'include',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `HTTP error! status: ${response.status}`);
      }
    } catch (error) {
      console.error('Failed to delete boundary:', error);
      throw error instanceof Error ? error : new Error('Failed to delete boundary');
    }
  }

  private validateBoundary(points: BoundaryPoint[]): { isValid: boolean; error?: string; area?: number } {
    if (points.length < 3) {
      return { isValid: false, error: 'Boundary must have at least 3 points' };
    }

    if (points.length > 100) {
      return { isValid: false, error: 'Boundary cannot have more than 100 vertices' };
    }

    let area = 0;
    for (let i = 0; i < points.length; i++) {
      const j = (i + 1) % points.length;
      area += points[i].lat * points[j].lng;
      area -= points[j].lat * points[i].lng;
    }
    area = Math.abs(area) / 2;

    const areaM2 = area * 111320 * 111320 * Math.cos(points[0].lat * Math.PI / 180);

    if (areaM2 < 10) {
      return { isValid: false, error: 'Boundary area must be at least 10 square meters' };
    }

    if (this.hasSelfIntersection(points)) {
      return { isValid: false, error: 'Boundary cannot intersect itself' };
    }

    return { isValid: true, area: areaM2 };
  }

  private hasSelfIntersection(points: BoundaryPoint[]): boolean {
    for (let i = 0; i < points.length; i++) {
      const line1 = {
        start: points[i],
        end: points[(i + 1) % points.length]
      };

      for (let j = i + 2; j < points.length; j++) {
        if (j === points.length - 1 && i === 0) continue;
        
        const line2 = {
          start: points[j],
          end: points[(j + 1) % points.length]
        };

        if (this.lineSegmentsIntersect(line1.start, line1.end, line2.start, line2.end)) {
          return true;
        }
      }
    }
    return false;
  }

  private lineSegmentsIntersect(p1: BoundaryPoint, q1: BoundaryPoint, p2: BoundaryPoint, q2: BoundaryPoint): boolean {
    const orientation = (p: BoundaryPoint, q: BoundaryPoint, r: BoundaryPoint) => {
      const val = (q.lng - p.lng) * (r.lat - q.lat) - (q.lat - p.lat) * (r.lng - q.lng);
      if (Math.abs(val) < 1e-10) return 0;
      return val > 0 ? 1 : 2;
    };

    const o1 = orientation(p1, q1, p2);
    const o2 = orientation(p1, q1, q2);
    const o3 = orientation(p2, q2, p1);
    const o4 = orientation(p2, q2, q1);

    return (o1 !== o2 && o3 !== o4);
  }

  isPointInsideBoundary(point: BoundaryPoint, boundary: Boundary): boolean {
    const points = boundary.points;
    let inside = false;
    
    for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
      if (((points[i].lat > point.lat) !== (points[j].lat > point.lat)) &&
          (point.lng < (points[j].lng - points[i].lng) * (point.lat - points[i].lat) / (points[j].lat - points[i].lat) + points[i].lng)) {
        inside = !inside;
      }
    }
    
    return inside;
  }
}

export const boundaryService = new BoundaryService();
export type { Boundary, BoundaryPoint, BoundaryCreateRequest, BoundaryUpdateRequest };
