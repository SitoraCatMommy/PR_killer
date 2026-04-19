import { ApiError, formatApiDetail } from '../api/client';
import { ru, translateApiMessage } from '../i18n/ru';
import { Alert, AlertDescription } from '@/components/ui/alert';

function localizeDetail(detail: unknown): string {
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const m = (detail as { message: unknown }).message;
    if (typeof m === 'string') return translateApiMessage(m);
  }
  return formatApiDetail(detail);
}

export function ApiErrorText({ error, className }: { error: unknown; className?: string }) {
  let message: string = ru.common.errorGeneric as string;
  if (error instanceof ApiError) {
    message = localizeDetail(error.detail);
  } else if (error instanceof Error) {
    message = error.message;
  }
  return (
    <Alert variant="destructive" className={className}>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
}
