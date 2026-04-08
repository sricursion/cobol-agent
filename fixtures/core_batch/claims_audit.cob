       IDENTIFICATION DIVISION.
       PROGRAM-ID. CLAIMS-AUDIT.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CLAIM-FILE ASSIGN TO "claims.dat".
           SELECT AUDIT-FILE ASSIGN TO "audit.dat".

       DATA DIVISION.
       FILE SECTION.
       FD  CLAIM-FILE.
       01  CLAIM-RECORD.
           05 CLAIM-ID            PIC X(10).
           05 CLAIM-AMOUNT        PIC 9(7).
           05 CLAIM-STATUS        PIC X(10).
       FD  AUDIT-FILE.
       01  AUDIT-RECORD           PIC X(60).

       WORKING-STORAGE SECTION.
       01  WS-EOF                 PIC X VALUE "N".
       01  WS-AUDIT-COUNT         PIC 9(4) VALUE 0.
       01  WS-TOTAL-AMOUNT        PIC 9(9) VALUE 0.

       PROCEDURE DIVISION.
       MAIN-PROCESS.
           OPEN INPUT CLAIM-FILE
           OPEN OUTPUT AUDIT-FILE
           PERFORM READ-CLAIM
           PERFORM UNTIL WS-EOF = "Y"
               PERFORM CHECK-CLAIM
               PERFORM READ-CLAIM
           END-PERFORM
           DISPLAY WS-AUDIT-COUNT WS-TOTAL-AMOUNT
           STOP RUN.

       READ-CLAIM.
           READ CLAIM-FILE
               AT END MOVE "Y" TO WS-EOF
           END-READ.

       CHECK-CLAIM.
           IF CLAIM-STATUS = "OPEN"
               ADD 1 TO WS-AUDIT-COUNT
               ADD CLAIM-AMOUNT TO WS-TOTAL-AMOUNT
               PERFORM WRITE-AUDIT
           END-IF.

       WRITE-AUDIT.
           WRITE AUDIT-RECORD.
