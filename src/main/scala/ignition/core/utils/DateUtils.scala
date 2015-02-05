package ignition.core.utils

import org.joda.time.{DateTimeZone, DateTime}
import org.joda.time.format.ISODateTimeFormat

object DateUtils {
  private val isoDateTimeFormatter = ISODateTimeFormat.dateTime()

  implicit def dateTimeOrdering: Ordering[DateTime] = Ordering.fromLessThan(_ isBefore _)

  implicit class DateTimeImprovements(val dateTime: DateTime) {
    def toIsoString = isoDateTimeFormatter.print(dateTime)

    def saneEqual(other: DateTime) =
      dateTime.withZone(DateTimeZone.UTC).isEqual(other.withZone(DateTimeZone.UTC))

    def isEqualOrAfter(other: DateTime) =
      dateTime.isAfter(other) || dateTime.saneEqual(other)

    def isEqualOrBefore(other: DateTime) =
      dateTime.isBefore(other) || dateTime.saneEqual(other)
  }
}
