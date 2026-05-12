import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { URLInput } from '../components/URLInput';

describe('URLInput', () => {
  it('renders the placeholder and the Score it button', () => {
    render(<URLInput onSubmit={() => {}} />);
    expect(screen.getByPlaceholderText('your-site.com')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Score it/i })).toBeInTheDocument();
  });

  it('disables the submit button when the input is empty', () => {
    render(<URLInput onSubmit={() => {}} />);
    expect(screen.getByRole('button', { name: /Score it/i })).toBeDisabled();
  });

  it('enables the submit button once the input is non-empty', () => {
    render(<URLInput onSubmit={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText('your-site.com'), {
      target: { value: 'stripe.com' },
    });
    expect(screen.getByRole('button', { name: /Score it/i })).not.toBeDisabled();
  });

  it('invokes onSubmit with the trimmed raw value on submit', () => {
    const onSubmit = vi.fn();
    render(<URLInput onSubmit={onSubmit} />);
    fireEvent.change(screen.getByPlaceholderText('your-site.com'), {
      target: { value: '  https://stripe.com/  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Score it/i }));
    expect(onSubmit).toHaveBeenCalledWith('https://stripe.com/');
  });

  it('does not invoke onSubmit when the input is whitespace-only', () => {
    const onSubmit = vi.fn();
    render(<URLInput onSubmit={onSubmit} />);
    fireEvent.change(screen.getByPlaceholderText('your-site.com'), {
      target: { value: '   ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Score it/i }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('guards the submit handler against whitespace-only input even via direct form submit', () => {
    const onSubmit = vi.fn();
    const { container } = render(<URLInput onSubmit={onSubmit} />);
    fireEvent.change(screen.getByPlaceholderText('your-site.com'), {
      target: { value: '   ' },
    });
    // Submitting the form bypasses the disabled-button guard.
    const form = container.querySelector('form')!;
    fireEvent.submit(form);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('honours the initial prop for the report-page compact form', () => {
    render(<URLInput compact initial="stripe.com" onSubmit={() => {}} />);
    expect(screen.getByDisplayValue('stripe.com')).toBeInTheDocument();
  });

  it('shows Scanning… and disables both controls when disabled', () => {
    render(<URLInput disabled initial="stripe.com" onSubmit={() => {}} />);
    expect(screen.getByRole('button', { name: /Scanning…/i })).toBeDisabled();
    expect(screen.getByDisplayValue('stripe.com')).toBeDisabled();
  });
});
