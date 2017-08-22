package ignition.core.cache

import akka.actor.ActorSystem
import ignition.core.cache.ExpiringMultiLevelCache.TimestampedValue
import org.scalatest.concurrent.ScalaFutures
import org.scalatest.{FlatSpec, Matchers}
import spray.caching.ExpiringLruLocalCache

import scala.concurrent.ExecutionContext.Implicits.global
import scala.concurrent.duration._
import scala.concurrent.{Await, Future}

class ExpiringMultipleLevelCacheSpec extends FlatSpec with Matchers with ScalaFutures {
  case class Data(s: String)
  implicit val scheduler = ActorSystem().scheduler

  "ExpiringMultipleLevelCache" should "calculate a value on cache miss and return it" in {
    val local = new ExpiringLruLocalCache[TimestampedValue[Data]](100)
    val cache = ExpiringMultiLevelCache[Data](1.minute, Option(local))
    Await.result(cache("key", () => Future.successful(Data("success"))), 1.minute) shouldBe Data("success")
  }

  it should "calculate a value on cache miss and return a failed future of the calculation" in {
    val local = new ExpiringLruLocalCache[TimestampedValue[Data]](100)
    val cache = ExpiringMultiLevelCache[Data](1.minute, Option(local))

    class MyException(s: String) extends Exception(s)

    val eventualCache = cache("key", () => Future.failed(new MyException("some failure")))
    whenReady(eventualCache.failed) { failure =>
      failure shouldBe a [MyException]
    }
  }

  it should "calculate a value on cache miss just once, the second call should be from cache hit" in {
    var myFailedRequestCount: Int = 0

    // TODO: Throw a 404 error
    class MyException(s: String) extends ArithmeticException(s) // Some NonFatal Exception
    def myFailedRequest(): Future[Nothing] = {
      println("calling myFailedRequest()")
      myFailedRequestCount = myFailedRequestCount + 1
      Future.failed(new MyException("some failure"))
    }

    val local = new ExpiringLruLocalCache[TimestampedValue[Data]](100)
    val cache = ExpiringMultiLevelCache[Data](1.minute, Option(local))

    val eventualCache = cache("key", myFailedRequest)
    whenReady(eventualCache.failed) { failure =>
      failure shouldBe a [MyException]
      myFailedRequestCount shouldBe 1
    }

    val eventualCache2 = cache("key", myFailedRequest)
    whenReady(eventualCache2.failed) { failure =>
      failure shouldBe a [MyException]
      myFailedRequestCount shouldBe 1
    }

  }

}
