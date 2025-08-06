import React from 'react';
import { Card, CardContent, Typography, Box } from '@mui/material';
import { WbSunny, Cloud, Grain } from '@mui/icons-material';

interface WeatherWidgetProps {
  weather: {
    temperature: number;
    humidity: number;
    condition: string;
  };
  style?: React.CSSProperties;
}

const WeatherWidget: React.FC<WeatherWidgetProps> = ({ weather, style }) => {
  const getWeatherIcon = (condition: string) => {
    if (condition.toLowerCase().includes('sun')) {
      return <WbSunny style={{ color: '#FFC107' }} />;
    }
    if (condition.toLowerCase().includes('cloud')) {
      return <Cloud style={{ color: '#90A4AE' }} />;
    }
    if (condition.toLowerCase().includes('rain')) {
      return <Grain style={{ color: '#4FC3F7' }} />;
    }
    return <WbSunny />;
  };

  return (
    <Box style={style}>
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Current Weather
          </Typography>
          <Box display="flex" alignItems="center">
            {getWeatherIcon(weather.condition)}
            <Typography variant="body1" style={{ marginLeft: '10px' }}>
              {weather.condition}
            </Typography>
          </Box>
          <Typography variant="body2">
            Temperature: {weather.temperature}°C
          </Typography>
          <Typography variant="body2">
            Humidity: {weather.humidity}%
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );
};

export default WeatherWidget;
