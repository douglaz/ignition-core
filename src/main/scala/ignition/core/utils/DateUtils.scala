package ignition.core.utils

import java.sql.Timestamp

import org.joda.time.{DateTime, DateTimeZone, Period, Seconds}
import org.joda.time.format.ISODateTimeFormat

object DateUtils {
  private val isoDateTimeFormatter = ISODateTimeFormat.dateTime().withZoneUTC()

  implicit def dateTimeOrdering: Ordering[DateTime] = Ordering.fromLessThan(_ isBefore _)
  implicit def periodOrdering: Ordering[Period] = Ordering.fromLessThan(_.toStandardSeconds.getSeconds <  _.toStandardSeconds.getSeconds)

  implicit def timestampOrdering: Ordering[Timestamp] = new Ordering[Timestamp] {
    def compare(x: Timestamp, y: Timestamp): Int = x compareTo y
  }

  implicit class DateTimeImprovements(val dateTime: DateTime) {
    def toIsoString = isoDateTimeFormatter.print(dateTime)

    def saneEqual(other: DateTime) =
      dateTime.withZone(DateTimeZone.UTC).isEqual(other.withZone(DateTimeZone.UTC))

    def isEqualOrAfter(other: DateTime) =
      dateTime.isAfter(other) || dateTime.saneEqual(other)

    def isEqualOrBefore(other: DateTime) =
      dateTime.isBefore(other) || dateTime.saneEqual(other)

    def isBetween(start: DateTime, end: DateTime) =
      dateTime.isAfter(start) && dateTime.isEqualOrBefore(end)
  }

  implicit class SecondsImprovements(val seconds: Seconds) {

    implicit def toScalaDuration: scala.concurrent.duration.FiniteDuration = {
      scala.concurrent.duration.Duration(seconds.getSeconds, scala.concurrent.duration.SECONDS)
    }

  }
}
