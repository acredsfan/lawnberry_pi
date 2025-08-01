import React from 'react';
import { Card as MuiCard, CardContent as MuiCardContent, CardHeader as MuiCardHeader, Typography } from '@mui/material';
import { styled } from '@mui/material/styles';

// Styled components to match the expected API
const StyledCard = styled(MuiCard)(({ theme }) => ({
  borderRadius: theme.spacing(1),
  boxShadow: '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
  border: '1px solid rgb(229 231 235)',
  '&:hover': {
    boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
  },
}));

const StyledCardHeader = styled(MuiCardHeader)(({ theme }) => ({
  paddingBottom: theme.spacing(1),
  '& .MuiCardHeader-title': {
    fontSize: '1.125rem',
    fontWeight: 600,
    lineHeight: 1.75,
  },
}));

const StyledCardContent = styled(MuiCardContent)(({ theme }) => ({
  paddingTop: theme.spacing(1),
  '&:last-child': {
    paddingBottom: theme.spacing(2),
  },
}));

// Card component
interface CardProps extends React.ComponentProps<typeof MuiCard> {
  children: React.ReactNode;
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ children, className, ...props }, ref) => (
    <StyledCard ref={ref} className={className} {...props}>
      {children}
    </StyledCard>
  )
);
Card.displayName = 'Card';

// CardHeader component
interface CardHeaderProps {
  children: React.ReactNode;
  className?: string;
}

export const CardHeader = React.forwardRef<HTMLDivElement, CardHeaderProps>(
  ({ children, className, ...props }, ref) => (
    <StyledCardHeader
      ref={ref}
      className={className}
      title={children}
      {...props}
    />
  )
);
CardHeader.displayName = 'CardHeader';

// CardTitle component
interface CardTitleProps {
  children: React.ReactNode;
  className?: string;
}

export const CardTitle = React.forwardRef<HTMLDivElement, CardTitleProps>(
  ({ children, className }, ref) => (
    <Typography
      ref={ref}
      variant="h6"
      component="h3"
      className={className}
      sx={{
        fontSize: '1.125rem',
        fontWeight: 600,
        lineHeight: 1.75,
        display: 'flex',
        alignItems: 'center',
      }}
    >
      {children}
    </Typography>
  )
);
CardTitle.displayName = 'CardTitle';

// CardContent component
interface CardContentProps extends React.ComponentProps<typeof MuiCardContent> {
  children: React.ReactNode;
}

export const CardContent = React.forwardRef<HTMLDivElement, CardContentProps>(
  ({ children, className, ...props }, ref) => (
    <StyledCardContent ref={ref} className={className} {...props}>
      {children}
    </StyledCardContent>
  )
);
CardContent.displayName = 'CardContent';
