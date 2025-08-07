import React from 'react';
import { Button as MuiButton } from '@mui/material';
import { styled } from '@mui/material/styles';

// Styled button component with variant support  
const StyledButton = styled(MuiButton, {
  shouldForwardProp: (prop) => prop !== 'customVariant'
})<{ customVariant?: 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link' }>(
  ({ theme, customVariant = 'default' }) => {
    const baseStyles = {
      fontSize: '0.875rem',
      fontWeight: 500,
      borderRadius: theme.spacing(0.75),
      padding: '0.5rem 1rem',
      textTransform: 'none' as const,
      minWidth: 'auto',
      '&:focus': {
        outline: '2px solid rgb(59 130 246)',
        outlineOffset: '2px',
      },
    };

    const variantStyles = {
      default: {
        backgroundColor: 'rgb(59 130 246)',
        color: 'white',
        '&:hover': {
          backgroundColor: 'rgb(37 99 235)',
        },
        '&:disabled': {
          backgroundColor: 'rgb(156 163 175)',
          color: 'white',
        },
      },
      destructive: {
        backgroundColor: 'rgb(239 68 68)',
        color: 'white',
        '&:hover': {
          backgroundColor: 'rgb(220 38 38)',
        },
        '&:disabled': {
          backgroundColor: 'rgb(156 163 175)',
          color: 'white',
        },
      },
      outline: {
        backgroundColor: 'transparent',
        color: 'rgb(55 65 81)',
        border: '1px solid rgb(209 213 219)',
        '&:hover': {
          backgroundColor: 'rgb(249 250 251)',
        },
        '&:disabled': {
          backgroundColor: 'transparent',
          color: 'rgb(156 163 175)',
          borderColor: 'rgb(229 231 235)',
        },
      },
      secondary: {
        backgroundColor: 'rgb(243 244 246)',
        color: 'rgb(55 65 81)',
        '&:hover': {
          backgroundColor: 'rgb(229 231 235)',
        },
        '&:disabled': {
          backgroundColor: 'rgb(249 250 251)',
          color: 'rgb(156 163 175)',
        },
      },
      ghost: {
        backgroundColor: 'transparent',
        color: 'rgb(55 65 81)',
        '&:hover': {
          backgroundColor: 'rgb(249 250 251)',
        },
        '&:disabled': {
          backgroundColor: 'transparent',
          color: 'rgb(156 163 175)',
        },
      },
      link: {
        backgroundColor: 'transparent',
        color: 'rgb(59 130 246)',
        textDecoration: 'underline',
        padding: 0,
        minHeight: 'auto',
        '&:hover': {
          backgroundColor: 'transparent',
          color: 'rgb(37 99 235)',
        },
        '&:disabled': {
          backgroundColor: 'transparent',
          color: 'rgb(156 163 175)',
        },
      },
    };

    return {
      ...baseStyles,
      ...variantStyles[customVariant],
    };
  }
);

interface ButtonProps extends Omit<React.ComponentProps<typeof MuiButton>, 'variant' | 'size'> {
  variant?: 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link';
  size?: 'sm' | 'default' | 'lg';
  children: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'default', size = 'default', className, children, ...props }, ref) => {
    const sizeStyles = {
      sm: { padding: '0.25rem 0.75rem', fontSize: '0.75rem' },
      default: { padding: '0.5rem 1rem', fontSize: '0.875rem' },
      lg: { padding: '0.75rem 1.5rem', fontSize: '1rem' },
    };

    // Map custom variants to MUI variants
    const getMuiVariant = (): 'text' | 'outlined' | 'contained' => {
      switch (variant) {
        case 'outline':
          return 'outlined';
        case 'ghost':
        case 'link':
          return 'text';
        default:
          return 'contained';
      }
    };

    // Get the MUI variant to use
    const muiVariant = getMuiVariant();

    return (
      <StyledButton
        ref={ref}
        variant={muiVariant}
        className={className}
        sx={sizeStyles[size]}
        customVariant={variant}
        {...props}
      >
        {children}
      </StyledButton>
    );
  }
);
Button.displayName = 'Button';
