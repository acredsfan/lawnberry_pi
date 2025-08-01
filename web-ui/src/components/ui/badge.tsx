import React from 'react';
import { Chip } from '@mui/material';
import { styled } from '@mui/material/styles';

// Styled badge component with variant support
const StyledBadge = styled(Chip)<{ variant?: 'default' | 'secondary' | 'destructive' | 'outline' }>(
  ({ theme, variant = 'default' }) => {
    const baseStyles = {
      fontSize: '0.75rem',
      fontWeight: 500,
      borderRadius: theme.spacing(0.75),
      height: 'auto',
      padding: '0.125rem 0.625rem',
      '& .MuiChip-label': {
        padding: 0,
      },
    };

    const variantStyles = {
      default: {
        backgroundColor: 'rgb(59 130 246)',
        color: 'white',
        '&:hover': {
          backgroundColor: 'rgb(37 99 235)',
        },
      },
      secondary: {
        backgroundColor: 'rgb(243 244 246)',
        color: 'rgb(55 65 81)',
        '&:hover': {
          backgroundColor: 'rgb(229 231 235)',
        },
      },
      destructive: {
        backgroundColor: 'rgb(239 68 68)',
        color: 'white',
        '&:hover': {
          backgroundColor: 'rgb(220 38 38)',
        },
      },
      outline: {
        backgroundColor: 'transparent',
        color: 'rgb(55 65 81)',
        border: '1px solid rgb(209 213 219)',
        '&:hover': {
          backgroundColor: 'rgb(249 250 251)',
        },
      },
    };

    return {
      ...baseStyles,
      ...variantStyles[variant],
    };
  }
);

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'secondary' | 'destructive' | 'outline';
  className?: string;
}

export const Badge = React.forwardRef<HTMLDivElement, BadgeProps>(
  ({ children, variant = 'default', className, ...props }, ref) => (
    <StyledBadge
      ref={ref}
      label={children}
      variant={variant}
      className={className}
      {...props}
    />
  )
);
Badge.displayName = 'Badge';
