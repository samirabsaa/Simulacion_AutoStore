export interface CsvRowError {
  row:    number;
  column: string;
  value:  string;
  reason: string;
}

export interface ValidationResultDTO {
  valid:  boolean;
  errors: CsvRowError[];
}
