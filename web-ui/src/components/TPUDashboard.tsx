import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { AlertCircle, Cpu, Zap, Activity, CheckCircle } from 'lucide-react';

interface TPUStatus {
  available: boolean;
  model_name: string;
  model_version: string;
  inference_count: number;
  average_inference_time_ms: number;
  fps_theoretical: number;
  lawn_optimized: boolean;
  tpu_used: boolean;
  cpu_fallback_active: boolean;
}

interface PerformanceMetrics {
  accuracy: number;
  precision: number;
  recall: number;
  f1_score: number;
}

const TPUDashboard: React.FC = () => {
  const [tpuStatus, setTpuStatus] = useState<TPUStatus | null>(null);
  const [performanceMetrics, setPerformanceMetrics] = useState<PerformanceMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchTPUStatus = async () => {
      try {
        const response = await fetch('/api/v1/vision/tpu/status');
        if (!response.ok) throw new Error('Failed to fetch TPU status');
        
        const data = await response.json();
        setTpuStatus(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    const fetchPerformanceMetrics = async () => {
      try {
        const response = await fetch('/api/v1/vision/tpu/performance');
        if (!response.ok) throw new Error('Failed to fetch performance metrics');
        
        const data = await response.json();
        setPerformanceMetrics(data);
      } catch (err) {
        console.error('Error fetching performance metrics:', err);
      }
    };

    fetchTPUStatus();
    fetchPerformanceMetrics();

    // Update every 5 seconds
    const interval = setInterval(() => {
      fetchTPUStatus();
      fetchPerformanceMetrics();
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5" />
            TPU Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-red-500" />
            TPU Status - Error
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-red-600 text-sm">{error}</div>
        </CardContent>
      </Card>
    );
  }

  const getStatusBadge = () => {
    if (!tpuStatus) return null;

    if (tpuStatus.available && tpuStatus.tpu_used) {
      return <Badge variant="default" className="bg-green-100 text-green-800">TPU Active</Badge>;
    } else if (tpuStatus.cpu_fallback_active) {
      return <Badge variant="secondary" className="bg-yellow-100 text-yellow-800">CPU Fallback</Badge>;
    } else {
      return <Badge variant="destructive">Offline</Badge>;
    }
  };

  const getPerformanceColor = (value: number, threshold: number = 0.8) => {
    if (value >= threshold) return 'text-green-600';
    if (value >= threshold * 0.7) return 'text-yellow-600';
    return 'text-red-600';
  };

  return (
    <div className="space-y-4">
      {/* Main Status Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Zap className="h-5 w-5" />
              TPU Status
            </div>
            {getStatusBadge()}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {tpuStatus && (
            <>
              {/* Model Information */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-sm font-medium text-gray-600">Model</div>
                  <div className="font-mono text-sm">{tpuStatus.model_name}</div>
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-600">Version</div>
                  <div className="font-mono text-sm">{tpuStatus.model_version}</div>
                </div>
              </div>

              {/* Performance Metrics */}
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center">
                  <div className="text-2xl font-bold text-blue-600">
                    {tpuStatus.average_inference_time_ms.toFixed(1)}ms
                  </div>
                  <div className="text-xs text-gray-600">Avg Inference</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-green-600">
                    {tpuStatus.fps_theoretical.toFixed(1)}
                  </div>
                  <div className="text-xs text-gray-600">Theoretical FPS</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-purple-600">
                    {tpuStatus.inference_count.toLocaleString()}
                  </div>
                  <div className="text-xs text-gray-600">Total Inferences</div>
                </div>
              </div>

              {/* Features */}
              <div className="flex gap-2 flex-wrap">
                {tpuStatus.lawn_optimized && (
                  <Badge variant="outline" className="text-green-600 border-green-600">
                    <CheckCircle className="h-3 w-3 mr-1" />
                    Lawn Optimized
                  </Badge>
                )}
                <Badge variant="outline" className="text-blue-600 border-blue-600">
                  <Activity className="h-3 w-3 mr-1" />
                  {tpuStatus.tpu_used ? 'TPU Accelerated' : 'CPU Processing'}
                </Badge>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Performance Metrics Card */}
      {performanceMetrics && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              Model Performance
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-sm font-medium">Accuracy</span>
                <span className={`text-sm font-bold ${getPerformanceColor(performanceMetrics.accuracy)}`}>
                  {(performanceMetrics.accuracy * 100).toFixed(1)}%
                </span>
              </div>
              <Progress value={performanceMetrics.accuracy * 100} className="h-2" />
            </div>

            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-sm font-medium">Precision</span>
                <span className={`text-sm font-bold ${getPerformanceColor(performanceMetrics.precision)}`}>
                  {(performanceMetrics.precision * 100).toFixed(1)}%
                </span>
              </div>
              <Progress value={performanceMetrics.precision * 100} className="h-2" />
            </div>

            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-sm font-medium">Recall</span>
                <span className={`text-sm font-bold ${getPerformanceColor(performanceMetrics.recall)}`}>
                  {(performanceMetrics.recall * 100).toFixed(1)}%
                </span>
              </div>
              <Progress value={performanceMetrics.recall * 100} className="h-2" />
            </div>

            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-sm font-medium">F1 Score</span>
                <span className={`text-sm font-bold ${getPerformanceColor(performanceMetrics.f1_score)}`}>
                  {(performanceMetrics.f1_score * 100).toFixed(1)}%
                </span>
              </div>
              <Progress value={performanceMetrics.f1_score * 100} className="h-2" />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Quick Actions */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-5 w-5" />
            Quick Actions
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <button
            className="w-full px-4 py-2 text-sm bg-blue-50 text-blue-700 rounded-md hover:bg-blue-100 transition-colors"
            onClick={() => window.open('/api/v1/vision/tpu/benchmark', '_blank')}
          >
            Run Performance Benchmark
          </button>
          <button
            className="w-full px-4 py-2 text-sm bg-gray-50 text-gray-700 rounded-md hover:bg-gray-100 transition-colors"
            onClick={() => window.location.reload()}
          >
            Refresh Status
          </button>
        </CardContent>
      </Card>
    </div>
  );
};

export default TPUDashboard;
