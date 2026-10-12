/**
 * Multi-line input with a required accessible label and an explicit description
 * slot, so an error or hint is never carried by placeholder text alone.
 */
import type { KeyboardEvent, Ref } from "react";
import { Label, Text, TextArea, TextField } from "react-aria-components";

export function TextAreaField({
  label,
  value,
  onChange,
  placeholder,
  description,
  errorMessage,
  isDisabled = false,
  rows = 2,
  onKeyDown,
  inputRef,
  testId,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  description?: string;
  errorMessage?: string;
  isDisabled?: boolean;
  rows?: number;
  onKeyDown?: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  inputRef?: Ref<HTMLTextAreaElement>;
  testId?: string;
}) {
  return (
    <TextField
      className="ea-field"
      value={value}
      onChange={onChange}
      isDisabled={isDisabled}
      isInvalid={errorMessage !== undefined}
    >
      <Label className="ea-visually-hidden">{label}</Label>
      <TextArea
        ref={inputRef}
        rows={rows}
        className="ea-input"
        placeholder={placeholder}
        data-testid={testId}
        onKeyDown={onKeyDown}
      />
      {description && (
        <Text slot="description" className="ea-field-description">
          {description}
        </Text>
      )}
      {errorMessage && (
        <Text slot="errorMessage" className="ea-field-error">
          {errorMessage}
        </Text>
      )}
    </TextField>
  );
}
