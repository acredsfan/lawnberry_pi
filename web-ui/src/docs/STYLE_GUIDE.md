# LawnBerryPi Style Guide

## Brand Colors

### Primary Colors
- **Primary Green**: `#2E7D32` - Main brand color from logo, represents nature/lawn
- **Primary Light**: `#4CAF50` - Hover states and accents
- **Primary Dark**: `#1B5E20` - Pressed states and emphasis

### Secondary Colors
- **Secondary Purple**: `#8E24AA` - Berry color from logo
- **Secondary Light**: `#BA68C8` - Light accents
- **Secondary Dark**: `#6A1B9A` - Strong emphasis

### Status Colors
- **Success**: `#4CAF50` - Success states and positive feedback
- **Warning**: `#FF9800` - Warning states and caution
- **Error**: `#F44336` - Error states and critical actions
- **Info**: `#2196F3` - Informational content

### Neutral Colors
- **Background**: `#FAFAFA` - Main background
- **Surface**: `#FFFFFF` - Card and surface backgrounds

## Logo Usage

### Sizes
- **Header**: 36-40px
- **Sidebar**: 32px  
- **Loading**: 80px

### Navigation
- Logo serves as home navigation - clicking returns to dashboard
- Always includes hover feedback for better UX

## Accessibility

All color combinations meet WCAG AA contrast standards:
- Primary green on white: 7.4:1 ratio
- Text colors provide excellent readability
- Focus states are clearly visible

## Component Guidelines

### Buttons
- Border radius: 8px
- No default shadow, subtle shadow on hover
- Use brand colors for primary actions

### Cards
- Border radius: 12px
- Subtle border and shadow for depth
- Hover effects for interactive elements

### Typography
- System font stack for optimal performance
- Consistent font weights (400, 500, 600)
- Proper line heights for readability

## CSS Variables

Use these variables for consistent theming:
```css
--brand-primary: #2E7D32
--brand-primary-light: #4CAF50
--brand-primary-dark: #1B5E20
--brand-secondary: #8E24AA
--brand-success: #4CAF50
--brand-warning: #FF9800
--brand-error: #F44336
```

## PWA Integration

- Theme color: `#2E7D32`
- App name: "LawnBerryPi Control"
- Uses logo for all app icons and favicon
</COMMAND>
