import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Badge } from '../../components/ui/badge'
import { Progress } from '../../components/ui/progress'
import { Button } from '../../components/ui/button'
import { Alert } from '../../components/ui/alert'

describe('UI Components', () => {
  let user: ReturnType<typeof userEvent.setup>

  beforeEach(() => {
    user = userEvent.setup()
  })

  describe('Card Components', () => {
    test('renders Card with content', () => {
      render(
        <Card>
          <CardHeader>
            <CardTitle>Test Title</CardTitle>
          </CardHeader>
          <CardContent>
            <p>Test content</p>
          </CardContent>
        </Card>
      )

      expect(screen.getByText('Test Title')).toBeInTheDocument()
      expect(screen.getByText('Test content')).toBeInTheDocument()
    })

    test('applies custom className to Card', () => {
      render(
        <Card className="custom-card">
          <CardContent>Content</CardContent>
        </Card>
      )

      const card = screen.getByText('Content').closest('.custom-card')
      expect(card).toBeInTheDocument()
    })

    test('supports nested card structure', () => {
      render(
        <Card>
          <CardHeader>
            <CardTitle>Outer Card</CardTitle>
          </CardHeader>
          <CardContent>
            <Card>
              <CardHeader>
                <CardTitle>Inner Card</CardTitle>
              </CardHeader>
              <CardContent>Inner content</CardContent>
            </Card>
          </CardContent>
        </Card>
      )

      expect(screen.getByText('Outer Card')).toBeInTheDocument()
      expect(screen.getByText('Inner Card')).toBeInTheDocument()
      expect(screen.getByText('Inner content')).toBeInTheDocument()
    })
  })

  describe('Badge Component', () => {
    test('renders badge with text', () => {
      render(<Badge>Active</Badge>)
      expect(screen.getByText('Active')).toBeInTheDocument()
    })

    test('applies variant styles', () => {
      render(<Badge variant="success">Success Badge</Badge>)
      const badge = screen.getByText('Success Badge')
      expect(badge).toBeInTheDocument()
    })

    test('supports custom className', () => {
      render(<Badge className="custom-badge">Custom</Badge>)
      const badge = screen.getByText('Custom')
      expect(badge).toHaveClass('custom-badge')
    })

    test('handles different sizes', () => {
      render(<Badge size="small">Small Badge</Badge>)
      const badge = screen.getByText('Small Badge')
      expect(badge).toBeInTheDocument()
    })
  })

  describe('Progress Component', () => {
    test('renders progress with value', () => {
      render(<Progress value={50} />)
      const progress = screen.getByRole('progressbar')
      expect(progress).toBeInTheDocument()
      expect(progress).toHaveAttribute('aria-valuenow', '50')
    })

    test('displays progress with max value', () => {
      render(<Progress value={75} max={100} />)
      const progress = screen.getByRole('progressbar')
      expect(progress).toHaveAttribute('aria-valuenow', '75')
      expect(progress).toHaveAttribute('aria-valuemax', '100')
    })

    test('supports indeterminate state', () => {
      render(<Progress />)
      const progress = screen.getByRole('progressbar')
      expect(progress).toBeInTheDocument()
    })

    test('applies custom className', () => {
      render(<Progress value={25} className="custom-progress" />)
      const progress = screen.getByRole('progressbar')
      expect(progress).toHaveClass('custom-progress')
    })
  })

  describe('Button Component', () => {
    test('renders button with text', () => {
      render(<Button>Click me</Button>)
      expect(screen.getByRole('button', { name: 'Click me' })).toBeInTheDocument()
    })

    test('handles click events', async () => {
      const handleClick = vi.fn()
      render(<Button onClick={handleClick}>Click me</Button>)
      
      await user.click(screen.getByRole('button', { name: 'Click me' }))
      expect(handleClick).toHaveBeenCalledTimes(1)
    })

    test('supports different variants', () => {
      render(<Button variant="outlined">Outlined Button</Button>)
      const button = screen.getByRole('button', { name: 'Outlined Button' })
      expect(button).toBeInTheDocument()
    })

    test('can be disabled', () => {
      render(<Button disabled>Disabled Button</Button>)
      const button = screen.getByRole('button', { name: 'Disabled Button' })
      expect(button).toBeDisabled()
    })

    test('supports loading state', () => {
      render(<Button loading>Loading Button</Button>)
      const button = screen.getByRole('button')
      expect(button).toBeDisabled()
    })

    test('supports different sizes', () => {
      render(<Button size="large">Large Button</Button>)
      const button = screen.getByRole('button', { name: 'Large Button' })
      expect(button).toBeInTheDocument()
    })
  })

  describe('Alert Component', () => {
    test('renders alert with message', () => {
      render(<Alert>This is an alert message</Alert>)
      expect(screen.getByText('This is an alert message')).toBeInTheDocument()
    })

    test('supports different severity levels', () => {
      render(<Alert severity="error">Error message</Alert>)
      const alert = screen.getByText('Error message')
      expect(alert).toBeInTheDocument()
    })

    test('can include title', () => {
      render(
        <Alert severity="warning" title="Warning">
          This is a warning message
        </Alert>
      )
      
      expect(screen.getByText('Warning')).toBeInTheDocument()
      expect(screen.getByText('This is a warning message')).toBeInTheDocument()
    })

    test('supports dismissible alerts', async () => {
      const handleClose = vi.fn()
      render(
        <Alert onClose={handleClose}>
          Dismissible alert
        </Alert>
      )
      
      const closeButton = screen.getByRole('button')
      await user.click(closeButton)
      expect(handleClose).toHaveBeenCalledTimes(1)
    })

    test('renders with custom icon', () => {
      render(
        <Alert icon={<span data-testid="custom-icon">!</span>}>
          Alert with custom icon
        </Alert>
      )
      
      expect(screen.getByTestId('custom-icon')).toBeInTheDocument()
      expect(screen.getByText('Alert with custom icon')).toBeInTheDocument()
    })

    test('applies custom className', () => {
      render(<Alert className="custom-alert">Custom styled alert</Alert>)
      const alert = screen.getByText('Custom styled alert')
      expect(alert.closest('.custom-alert')).toBeInTheDocument()
    })
  })

  describe('Component Integration', () => {
    test('components work together in complex layout', () => {
      render(
        <Card>
          <CardHeader>
            <CardTitle>
              Dashboard <Badge variant="success">Online</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Alert severity="info">System is running normally</Alert>
            <div style={{ margin: '16px 0' }}>
              <Progress value={85} />
            </div>
            <Button>Refresh Status</Button>
          </CardContent>
        </Card>
      )

      expect(screen.getByText('Dashboard')).toBeInTheDocument()
      expect(screen.getByText('Online')).toBeInTheDocument()
      expect(screen.getByText('System is running normally')).toBeInTheDocument()
      expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '85')
      expect(screen.getByRole('button', { name: 'Refresh Status' })).toBeInTheDocument()
    })
  })
})
