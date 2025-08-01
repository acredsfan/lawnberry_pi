import React from 'react';
import { Alert as MuiAlert, AlertTitle } from '@mui/material';
import { styled } from '@mui/material/styles';

// Styled alert component
const StyledAlert = styled(MuiAlert)(({ theme }) => ({
  borderRadius: theme.spacing(0.75),
  fontSize: '0.875rem',
  '& .MuiAlert-message': {
    padding: 0,
  },
  '& .MuiAlert-icon': {
    fontSize: '1.25rem',
  },
}));

interface AlertProps extends React.ComponentProps<typeof MuiAlert> {
  variant?: 'default' | 'destructive';
  children: React.ReactNode;
}

export const Alert = React.forwardRef<HTMLDivElement, AlertProps>(
  ({ variant = 'default', severity, children, className, ...props }, ref) => {
    // Map custom variants to Material-UI severity
    const getMuiSeverity = () => {
      if (severity) return severity;
      
      switch (variant) {
        case 'destructive':
          return 'error';
        case 'default':
        default:
          return 'info';
      }
    };

    return (
      <StyledAlert
        ref={ref}
        severity={getMuiSeverity()}
        className={className}
        {...props}
      >
        {children}
      </StyledAlert>
    );
  }
);
Alert.displayName = 'Alert';

// Export AlertTitle for compatibility
export { AlertTitle };
