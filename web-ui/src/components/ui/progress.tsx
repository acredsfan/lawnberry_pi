import React from 'react';
import { LinearProgress } from '@mui/material';
import { styled } from '@mui/material/styles';

// Styled progress component
const StyledProgress = styled(LinearProgress)(({ theme }) => ({
  height: 8,
  borderRadius: theme.spacing(1),
  backgroundColor: 'rgb(229 231 235)',
  '& .MuiLinearProgress-bar': {
    borderRadius: theme.spacing(1),
    backgroundColor: 'rgb(59 130 246)',
  },
  // Support for custom height via className
  '&.h-2': {
    height: 8,
  },
  '&.h-3': {
    height: 12,
  },
  '&.h-4': {
    height: 16,
  },
}));

interface ProgressProps {
  value?: number;
  max?: number;
  className?: string;
}

export const Progress = React.forwardRef<HTMLDivElement, ProgressProps>(
  ({ value = 0, max = 100, className, ...props }, ref) => {
    const normalizedValue = Math.min(Math.max((value / max) * 100, 0), 100);
    
    return (
      <StyledProgress
        ref={ref}
        variant="determinate"
        value={normalizedValue}
        className={className}
        {...props}
      />
    );
  }
);
Progress.displayName = 'Progress';
