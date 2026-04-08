       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYROLL-REPORT.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT EMPLOYEE-FILE ASSIGN TO "employee.dat".

       DATA DIVISION.
       FILE SECTION.
       FD  EMPLOYEE-FILE.
       01  EMPLOYEE-RECORD.
           05 EMP-ID              PIC X(5).
           05 EMP-NAME            PIC X(20).
           05 EMP-PAY             PIC 9(5).

       WORKING-STORAGE SECTION.
       01  WS-TOTAL-PAY          PIC 9(7) VALUE 0.
       01  WS-EOF                PIC X VALUE "N".

       PROCEDURE DIVISION.
       MAIN-PARA.
           OPEN INPUT EMPLOYEE-FILE
           PERFORM READ-EMPLOYEE
           PERFORM UNTIL WS-EOF = "Y"
               PERFORM PRINT-EMPLOYEE
               PERFORM READ-EMPLOYEE
           END-PERFORM
           DISPLAY WS-TOTAL-PAY
           STOP RUN.

       READ-EMPLOYEE.
           READ EMPLOYEE-FILE
               AT END MOVE "Y" TO WS-EOF
           END-READ.

       PRINT-EMPLOYEE.
           ADD EMP-PAY TO WS-TOTAL-PAY
           DISPLAY EMP-NAME EMP-PAY.
