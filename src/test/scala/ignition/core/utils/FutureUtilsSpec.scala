package ignition.core.utils
import ignition.core.utils.FutureUtils._
import org.scalatest._
import org.scalatest.concurrent.ScalaFutures

import scala.concurrent.ExecutionContext.Implicits.global
import scala.concurrent.Future
import scala.concurrent.duration._

class FutureUtilsSpec extends FlatSpec with Matchers with ScalaFutures {
  "FutureUtils" should "provide toLazyIterable" in {
    val timesCalled = collection.mutable.Map.empty[Int, Int].withDefaultValue(0)

    val generators = (0 until 20).map { i => () => Future { timesCalled(i) += 1 ; i } }
    val iterable = generators.toLazyIterable()
    val iterator = iterable.toIterator
    timesCalled.forall { case (_, count) => count == 0 } shouldBe true

    whenReady(iterator.next(), timeout(2.seconds)) { _ => () }

    timesCalled(0) shouldBe 1

    (1 until 20).foreach { i => timesCalled(i) shouldBe 0 }

    whenReady(Future.sequence(iterator), timeout(5.seconds)) { result =>
      result.toList shouldBe (1 until 20).toList
    }

    (0 until 20).foreach { i => timesCalled(i) shouldBe 1 }
  }

  it should "provide collectAndTake" in {
    val timesCalled = collection.mutable.Map.empty[Int, Int].withDefaultValue(0)
    val iterable = (0 until 30).map { i =>
      () =>
        Future {
          synchronized {
            timesCalled(i) += 1
          }
          i
        }
    }.toLazyIterable()

    val expectedRange = Range(5, 15)

    val f: Future[List[Int]] = iterable.collectAndTake({ case i if expectedRange.contains(i) => i }, n = expectedRange.size)

    whenReady(f, timeout(5.seconds)) { result =>
      result shouldBe expectedRange.toList
    }

    (0 until 20).foreach { i => timesCalled(i) shouldBe 1 } // 2 batches of size 10
    (20 until 30).foreach { i => timesCalled(i) shouldBe 0 } // last batch won't be ran
  }

}
